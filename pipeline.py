#!/usr/bin/env python3
"""Thrift-Cycle Daily Pipeline — Orchestrates the full data collection and scoring.
"""

import json
import sqlite3
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browse_api import get_active_counts
from finding_api import get_sold_stats

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "thrift_cycle.db")
CAT_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "category_map.json")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# All keywords
KEYWORDS = [
    "Birkenstock Arizona", "Birkenstock Boston", "Birkenstock Gizeh", "Birkenstock Madrid",
    "Birkenstock EVA", "Lowa Renegade GTX", "Lowa Camino GTX", "Meindl Bhutan",
    "Meindl Ortler", "Meindl Borneo", "Ortlieb Back-Roller", "Ortlieb Velocity",
    "Jack Wolfskin 3in1 Jacket", "Jack Wolfskin DNA", "Deuter Aircontact 65+10",
    "Deuter Futura", "Vaude Brenta", "Patagonia Retro-X Fleece", "Patagonia Better Sweater",
    "Patagonia Nano Puff", "Arc'teryx Beta LT", "Arc'teryx Atom LT", "Arc'teryx Zeta SL",
    "Vintage Levi's 501", "Levi's 501 Made in USA", "Miu Miu Ballerinas", "Repetto Ballerinas",
    "Chanel Ballerinas",
    "Vintage Levi's 501 80s", "Vintage Levi's 501 90s", "Levi's 501 Red Line",
    "Levi's 501 Shrink-to-Fit", "Patagonia Houdini", "Patagonia Synchilla",
    "Arc'teryx Alpha SV", "Arc'teryx Gamma MX", "Tory Burch Ballet Flats",
    "Miu Miu Ballet Flats",
]

MARKETPLACES = ["de", "us"]

# Sellability Index thresholds
HOT_THRESHOLD = 0.60
WARM_THRESHOLD = 0.30

def init_db():
    """Initialize SQLite database with required tables."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("""CREATE TABLE IF NOT EXISTS snapshots (
        date TEXT,
        keyword TEXT,
        marketplace TEXT,
        buying_option TEXT,
        active_count INTEGER,
        sold_count INTEGER,
        avg_price REAL,
        median_price REAL,
        min_price REAL,
        max_price REAL,
        str REAL,
        sellability_index REAL,
        confidence TEXT,
        trend_direction TEXT,
        PRIMARY KEY (date, keyword, marketplace, buying_option)
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT,
        marketplace TEXT,
        item_id TEXT,
        title TEXT,
        price REAL,
        currency TEXT,
        selling_state TEXT,
        category_id TEXT,
        end_time TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    
    c.execute("""CREATE INDEX IF NOT EXISTS idx_snapshots_date ON snapshots(date)""")
    c.execute("""CREATE INDEX IF NOT EXISTS idx_snapshots_keyword ON snapshots(keyword, marketplace)""")
    c.execute("""CREATE INDEX IF NOT EXISTS idx_listings_created ON listings(created_at)""")
    
    conn.commit()
    conn.close()

def calculate_sellability(sold_count, active_count, avg_price=None):
    """Calculate sellability index with confidence tag.
    
    Index = (SoldCount / (SoldCount + ActiveCount)) × ConfidenceMultiplier
    
    Confidence:
    - HIGH: 100+ sold in 30d
    - MEDIUM: 30-99 sold  
    - LOW: <30 sold
    """
    if sold_count == 0:
        return 0.0, "LOW"
    
    total = sold_count + active_count
    if total == 0:
        return 0.0, "LOW"
    
    # Base sellability rate
    index = sold_count / total
    
    # Confidence multiplier
    if sold_count >= 100:
        confidence = "HIGH"
        multiplier = 1.0
    elif sold_count >= 30:
        confidence = "MEDIUM"
        multiplier = 0.85
    else:
        confidence = "LOW"
        multiplier = 0.7
    
    index = round(index * multiplier, 4)
    return index, confidence

def calculate_trend(keyword, marketplace, current_str, conn):
    """Calculate trend direction by comparing with last week's STR.
    
    Returns: ▲ heating up / ▼ cooling down / → stable
    """
    today = datetime.utcnow().strftime("%Y-%m-%d")
    week_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    c = conn.cursor()
    c.execute("""
        SELECT str FROM snapshots 
        WHERE keyword = ? AND marketplace = ? AND date = ? 
        ORDER BY date DESC LIMIT 1
    """, (keyword, marketplace, week_ago))
    
    row = c.fetchone()
    if not row:
        return "→"  # New, no trend data
    
    prev_str = row[0]
    diff = current_str - prev_str
    
    if diff > 0.05:
        return "▲"
    elif diff < -0.05:
        return "▼"
    else:
        return "→"

def get_score_band(index):
    """Return score band label."""
    if index >= HOT_THRESHOLD:
        return "HOT"
    elif index >= WARM_THRESHOLD:
        return "WARM"
    else:
        return "COLD"

def run_pipeline(keywords=None, marketplaces=None, days=30):
    """Run the full daily pipeline."""
    if keywords is None:
        keywords = KEYWORDS
    if marketplaces is None:
        marketplaces = MARKETPLACES
    
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    # Load category map
    category_map = None
    if os.path.exists(CAT_MAP_PATH):
        with open(CAT_MAP_PATH) as f:
            category_map = json.load(f)
    
    # Init DB
    init_db()
    conn = sqlite3.connect(DB_PATH)
    
    results = []
    errors = []
    
    print(f"=== Thrift-Cycle Pipeline — {today} ===\n")
    print(f"Keywords: {len(keywords)} | Markets: {', '.join(marketplaces)}\n")
    
    for i, keyword in enumerate(keywords, 1):
        print(f"[{i}/{len(keywords)}] {keyword}")
        
        for mkt in marketplaces:
            cat_id = None
            if category_map and keyword in category_map:
                cat_info = category_map[keyword].get(mkt)
                if cat_info:
                    cat_id = cat_info.get("category_id")
            
            # Active counts
            try:
                active = get_active_counts(keyword, mkt, cat_id)
            except Exception as e:
                errors.append(f"{keyword} ({mkt}) browse: {e}")
                continue
            
            # Sold stats
            try:
                sold = get_sold_stats(keyword, mkt, cat_id, days)
            except Exception as e:
                errors.append(f"{keyword} ({mkt}) finding: {e}")
                continue
            
            # Calculate metrics
            total_active = active.get("total", 0)
            total_sold = sold.get("sold_count", 0)
            avg_price = sold.get("avg_price", 0)
            
            sellability, confidence = calculate_sellability(total_sold, total_active, avg_price)
            trend = calculate_trend(keyword, mkt, sellability, conn)
            band = get_score_band(sellability)
            
            # Store in DB
            c = conn.cursor()
            for option in ["all", "fixed_price", "auction"]:
                option_sold = total_sold  # Finding API doesn't split by option
                option_active = active.get(option, 0)
                str_val = round(option_sold / (option_sold + option_active) * 100, 1) if (option_sold + option_active) > 0 else 0
                
                c.execute("""INSERT OR REPLACE INTO snapshots 
                    (date, keyword, marketplace, buying_option, active_count, sold_count, 
                     avg_price, median_price, min_price, max_price, str, sellability_index, 
                     confidence, trend_direction)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (today, keyword, mkt, option, option_active, option_sold,
                     sold.get("avg_price", 0), sold.get("median_price", 0),
                     sold.get("min_price", 0), sold.get("max_price", 0),
                     str_val, sellability, confidence, trend))
            
            conn.commit()
            
            results.append({
                "keyword": keyword,
                "marketplace": mkt,
                "active": total_active,
                "sold": total_sold,
                "avg_price": avg_price,
                "sellability": sellability,
                "confidence": confidence,
                "trend": trend,
                "band": band,
            })
            
            print(f"  {mkt}: active={total_active}, sold={total_sold}, "
                  f"avg=${avg_price}, index={sellability:.2f} [{band}] {trend}")
    
    # Cleanup: delete listings older than 30d
    cutoff = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    conn.execute("DELETE FROM listings WHERE created_at < ?", (cutoff,))
    conn.commit()
    conn.close()
    
    # Save raw data
    os.makedirs(DATA_DIR, exist_ok=True)
    data_path = os.path.join(DATA_DIR, f"{today}.json")
    with open(data_path, "w") as f:
        json.dump({"date": today, "results": results, "errors": errors}, f, indent=2)
    
    print(f"\n=== Pipeline Complete ===")
    print(f"Results: {len(results)} | Errors: {len(errors)}")
    print(f"Data saved: {data_path}")
    
    if errors:
        print(f"\nErrors:")
        for e in errors:
            print(f"  - {e}")
    
    return results

if __name__ == "__main__":
    # Run with a small test set first
    test_keywords = ["Birkenstock Arizona", "Patagonia Nano Puff"]
    print("Running test pipeline with 2 keywords...\n")
    results = run_pipeline(keywords=test_keywords, marketplaces=["us"])
    
    print(f"\n=== Test Results ===")
    for r in results:
        print(f"  {r['keyword']} ({r['marketplace']}): "
              f"active={r['active']}, sold={r['sold']}, "
              f"avg=${r['avg_price']}, index={r['sellability']:.2f} [{r['band']}] {r['trend']}")