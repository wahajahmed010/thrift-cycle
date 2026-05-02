#!/usr/bin/env python3
"""Thrift-Cycle Daily Pipeline — Orchestrates the full data collection and scoring.

Pipeline flow: auth → taxonomy → browse → finding → calculate → store → report
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dns_patch
from ebay_auth import get_token
from browse_api import get_active_counts
from finding_api import get_sold_stats
from fallback_cache import get_cached_sold_stats

BASE_DIR = Path(__file__).parent.resolve()
DB_PATH = BASE_DIR / "thrift_cycle.db"
CAT_MAP_PATH = BASE_DIR / "category_map.json"
DATA_DIR = BASE_DIR / "data"

# ---------------------------------------------------------------------------
# Keywords per market (from PROJECT-PLAN.md)
# ---------------------------------------------------------------------------
KEYWORDS_DE = [
    "Birkenstock Arizona", "Birkenstock Boston", "Birkenstock Gizeh",
    "Birkenstock Madrid", "Birkenstock EVA",
    "Lowa Renegade GTX", "Lowa Camino GTX",
    "Meindl Bhutan", "Meindl Ortler", "Meindl Borneo",
    "Ortlieb Back-Roller", "Ortlieb Velocity",
    "Jack Wolfskin 3in1 Jacket", "Jack Wolfskin DNA",
    "Deuter Aircontact 65+10", "Deuter Futura",
    "Vaude Brenta",
    "Patagonia Retro-X Fleece", "Patagonia Better Sweater", "Patagonia Nano Puff",
    "Arc'teryx Beta LT", "Arc'teryx Atom LT", "Arc'teryx Zeta SL",
    "Vintage Levi's 501", "Levi's 501 Made in USA",
    "Miu Miu Ballerinas", "Repetto Ballerinas", "Chanel Ballerinas",
]

KEYWORDS_US = [
    "Birkenstock Arizona", "Birkenstock Boston", "Birkenstock Gizeh",
    "Birkenstock EVA",
    "Vintage Levi's 501 80s", "Vintage Levi's 501 90s",
    "Levi's 501 Red Line", "Levi's 501 Shrink-to-Fit",
    "Patagonia Retro-X Fleece", "Patagonia Better Sweater", "Patagonia Nano Puff",
    "Patagonia Houdini", "Patagonia Synchilla",
    "Arc'teryx Beta LT", "Arc'teryx Atom LT", "Arc'teryx Alpha SV",
    "Arc'teryx Zeta SL", "Arc'teryx Gamma MX",
    "Lowa Renegade GTX", "Meindl Bhutan",
    "Tory Burch Ballet Flats", "Miu Miu Ballet Flats",
]

BUYING_OPTIONS = ["FIXED_PRICE", "AUCTION"]

# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
def init_db():
    """Initialize SQLite DB with required tables."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS snapshots (
        date TEXT NOT NULL,
        keyword TEXT NOT NULL,
        marketplace TEXT NOT NULL,
        buying_option TEXT NOT NULL,
        active_count INTEGER DEFAULT 0,
        sold_count INTEGER DEFAULT 0,
        avg_price REAL DEFAULT 0,
        str REAL DEFAULT 0,
        sellability_index REAL DEFAULT 0,
        confidence TEXT DEFAULT 'LOW',
        trend_direction TEXT DEFAULT '→',
        PRIMARY KEY (date, keyword, marketplace, buying_option)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT,
        marketplace TEXT,
        item_id TEXT,
        title TEXT,
        price REAL,
        sold_date TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_snap_date ON snapshots(date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_snap_kw ON snapshots(keyword, marketplace)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_list_created ON listings(created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_list_kw ON listings(keyword, marketplace)")

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Sellability calculation (from technical-design.md)
# ---------------------------------------------------------------------------
def _delta_demand(keyword, marketplace, current_sold_7d, conn):
    """Week-over-week change in SoldUnits_7d. Returns float (e.g. 1.08 = +8%)."""
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    c = conn.cursor()
    c.execute("""
        SELECT sold_count FROM snapshots
        WHERE keyword = ? AND marketplace = ? AND date = ? AND buying_option = 'all'
    """, (keyword, marketplace, week_ago))
    row = c.fetchone()
    if not row or not row[0] or row[0] == 0:
        return 1.0
    prev = row[0]
    # Normalize: if current_7d not available, scale from 30d
    ratio = current_sold_7d / prev if prev else 1.0
    return round(ratio, 2)


def calculate_metrics(sold_count, active_count, confidence=None, sold_7d_estimate=None, avg_listing_age_days=30):
    """Calculate STR, Sellability Index, and confidence tag.

    Per technical-design.md:
      STR% = sold_count / (sold_count + active_count) * 100
      Index_raw = (SoldUnits_30d / ActiveListings) * delta_demand
      ConfidenceMultiplier = min(1.0, SoldUnits_30d / 30)
      ListingAgePenalty = 1 - min(1.0, AvgListingAge_days / 90)
      Index_final = Index_raw * ConfidenceMultiplier * ListingAgePenalty
    """
    total = sold_count + active_count
    str_pct = round((sold_count / total) * 100, 1) if total > 0 else 0.0

    # Index raw with delta demand
    index_raw = (sold_count / active_count) if active_count > 0 else 0.0
    delta_demand = sold_7d_estimate if sold_7d_estimate else 1.0
    index_raw *= delta_demand

    # Confidence multiplier
    if sold_count >= 100:
        conf_tag = "HIGH"
        multiplier = 1.0
    elif sold_count >= 30:
        conf_tag = "MEDIUM"
        multiplier = 0.75
    else:
        conf_tag = "LOW"
        multiplier = min(1.0, sold_count / 30)

    # Listing age penalty (estimate 30 days if unknown)
    listing_age_penalty = 1.0 - min(1.0, avg_listing_age_days / 90)
    listing_age_penalty = max(0.0, listing_age_penalty)

    index_final = index_raw * multiplier * listing_age_penalty
    index_final = round(index_final, 4)

    # Override confidence tag if caller provided one
    if confidence:
        conf_tag = confidence

    return {
        "str": str_pct,
        "index_raw": round(index_raw, 4),
        "index_final": index_final,
        "confidence": conf_tag,
    }


def calculate_trend(keyword, marketplace, current_index, conn):
    """Compare current index vs last week's for this keyword/market."""
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    c = conn.cursor()
    c.execute("""
        SELECT sellability_index FROM snapshots
        WHERE keyword = ? AND marketplace = ? AND date = ? AND buying_option = 'all'
    """, (keyword, marketplace, week_ago))
    row = c.fetchone()
    if not row or row[0] is None:
        return "→"
    prev = row[0]
    diff = current_index - prev
    if diff > 0.02:
        return "▲"
    elif diff < -0.02:
        return "▼"
    return "→"


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def store_listings(keyword, marketplace, items):
    """Store individual sold items in listings table for dedup/relist detection."""
    if not items:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for item in items:
        c.execute("""
            INSERT OR IGNORE INTO listings
            (keyword, marketplace, item_id, title, price, sold_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            keyword, marketplace,
            item.get("item_id", ""),
            item.get("title", "")[:200],
            item.get("price", 0),
            item.get("end_time", "")[:10],  # date part only
        ))
    conn.commit()
    conn.close()


def run_pipeline(keywords_de=None, keywords_us=None, days=30):
    """Run the full daily pipeline."""
    keywords_de = keywords_de or KEYWORDS_DE
    keywords_us = keywords_us or KEYWORDS_US
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    init_db()

    # Load category map
    category_map = {}
    if CAT_MAP_PATH.exists():
        with open(CAT_MAP_PATH) as f:
            category_map = json.load(f)

    results = []
    errors = []

    print(f"=== Thrift-Cycle Pipeline — {today} ===\n")
    total_kws = len(keywords_de) + len(keywords_us)
    processed = 0

    all_keywords = [("de", keywords_de), ("us", keywords_us)]

    for mkt, keywords in all_keywords:
        mp_label = "EBAY-DE" if mkt == "de" else "EBAY-US"
        for keyword in keywords:
            processed += 1
            print(f"[{processed}/{total_kws}] {keyword} ({mkt.upper()})")

            cat_id = None
            if keyword in category_map and mkt in category_map[keyword]:
                cat_id = category_map[keyword][mkt].get("category_id")

            # --- Browse API: active counts ---
            try:
                active = get_active_counts(keyword, mkt, cat_id)
            except Exception as e:
                err = f"{keyword} ({mkt}) browse: {e}"
                print(f"  ERROR: {err}")
                errors.append(err)
                continue

            total_active = active.get("total", 0)
            active_fixed = active.get("fixed_price", 0)
            active_auction = active.get("auction", 0)

            # --- Finding API: sold data ---
            try:
                sold = get_sold_stats(keyword, mkt, cat_id, days)
            except Exception as e:
                err = f"{keyword} ({mkt}) finding exception: {e}"
                print(f"  ERROR: {err}")
                errors.append(err)
                continue

            # BUG FIX: check for API-level errors returned in the dict
            if sold.get("error"):
                # Try fallback cache if API failed (rate limit, etc.)
                cached = get_cached_sold_stats(keyword, mkt)
                if cached:
                    print(f"  ⚠️  API error, using cached data from {cached['_cache_date']}")
                    sold = cached
                else:
                    err = f"{keyword} ({mkt}) finding API error: {sold['error']}"
                    print(f"  ERROR: {err}")
                    errors.append(err)
                    continue

            total_sold = sold.get("sold_count", 0)
            avg_price = sold.get("avg_price", 0)
            items = sold.get("items", [])
            is_cached = sold.get("_cached", False)

            # Store individual listings
            store_listings(keyword, mkt, items)

            # --- Calculate metrics per buying option ---
            by_option = sold.get("by_option", {})

            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row

            for option in ["all"] + BUYING_OPTIONS:
                if option == "all":
                    option_active = total_active
                    option_sold = total_sold
                    option_avg = avg_price
                else:
                    opt_data = by_option.get(option, {})
                    option_sold = opt_data.get("sold_count", 0)
                    option_avg = opt_data.get("avg_price", 0)
                    option_active = active_fixed if option == "FIXED_PRICE" else active_auction

                metrics = calculate_metrics(
                    option_sold,
                    option_active,
                )

                str_val = metrics["str"]
                index_final = metrics["index_final"]
                confidence = metrics["confidence"]

                trend = calculate_trend(keyword, mkt, index_final, conn) if option == "all" else "→"

                c = conn.cursor()
                c.execute("""
                    INSERT OR REPLACE INTO snapshots
                    (date, keyword, marketplace, buying_option,
                     active_count, sold_count, avg_price, str,
                     sellability_index, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    today, keyword, mkt, option,
                    option_active, option_sold, option_avg,
                    str_val, index_final, confidence,
                ))

                conn.commit()

                if option == "all":
                    band = "🔥 HOT" if index_final >= 0.60 else "🌡️ WARM" if index_final >= 0.30 else "❄️ COLD"
                    print(f"  active={total_active}, sold={total_sold}, "
                          f"avg=${avg_price:.0f}, STR={str_val:.1f}%, "
                          f"index={index_final:.3f} [{confidence}] {trend}")

            conn.close()

            results.append({
                "keyword": keyword,
                "marketplace": mkt,
                "active": total_active,
                "sold": total_sold,
                "avg_price": avg_price,
                "sellability": index_final,
                "confidence": confidence,
                "trend": trend,
            })

    # --- Retention cleanup ---
    cutoff_listings = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    cutoff_snapshots = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM listings WHERE created_at < ?", (cutoff_listings,))
    conn.execute("DELETE FROM snapshots WHERE date < ?", (cutoff_snapshots,))
    conn.commit()
    conn.close()

    # --- Save raw data ---
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data_path = DATA_DIR / f"{today}.json"
    with open(data_path, "w") as f:
        json.dump({"date": today, "results": results, "errors": errors}, f, indent=2)

    # --- Generate report ---
    from report import generate_report
    messages = generate_report(date=today)

    print(f"\n=== Pipeline Complete ===")
    print(f"Results: {len(results)} | Errors: {len(errors)}")
    print(f"Data saved: {data_path}")
    if messages:
        print(f"Report: {len(messages)} message(s) generated")

    return results, messages, errors


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    # Use --full for all keywords, --test for 2-keyword test (default: full)
    if "--test" in sys.argv:
        test_de = ["Birkenstock Arizona", "Patagonia Nano Puff"]
        test_us = ["Birkenstock Arizona", "Patagonia Nano Puff"]
        print("Running test pipeline with 4 keyword-market combos...\n")
        results, messages, errors = run_pipeline(keywords_de=test_de, keywords_us=test_us)
    else:
        print("Running full pipeline with all keywords...\n")
        results, messages, errors = run_pipeline()

    print(f"\n=== Pipeline Results ===")
    hot = [r for r in results if r["sellability"] >= 0.60]
    warm = [r for r in results if 0.30 <= r["sellability"] < 0.60]
    cold = [r for r in results if r["sellability"] < 0.30]
    print(f"  HOT: {len(hot)}, WARM: {len(warm)}, COLD: {len(cold)}, Total: {len(results)}")
    for r in sorted(results, key=lambda x: x["sellability"], reverse=True)[:10]:
        band = "HOT" if r["sellability"] >= 0.60 else "WARM" if r["sellability"] >= 0.30 else "COLD"
        print(f"  {r['keyword']} ({r['marketplace']}): "
              f"active={r['active']}, sold={r['sold']}, "
              f"avg=${r['avg_price']:.0f}, index={r['sellability']:.3f} [{band}] {r['trend']}")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
