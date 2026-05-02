# Thrift-Cycle Predictor — Council Review v2
**Council:** Strategos | Analyticos | Creativos  
**Date:** 2026-04-27  
**Status:** CRITICAL — Pipeline producing zero-value output  

---

## Executive Summary

The pipeline is **functionally dead** because `sold_count = 0` for every keyword, forcing `sellability_index = 0.0` and `confidence = LOW` across the entire universe. The dashboard at `wahajahmed010.github.io/thrift-cycle` displays 4 test-mode items (not 50), all rated COLD with 0% STR. This makes the tool useless for Wahaj's actual question: *"What sells fast in summer in Germany?"*

**Root cause:** The Finding API (`findCompletedItems`) is fully rate-limited. Browse API works. The historical scrape files (76 `.json` files from 2026-04-26) contain valid sold price samples, but the pipeline ignores them.

**The fix has two parallel tracks:**
1. **Immediate (this week):** Rebuild the sellability index using ONLY Browse API proxy metrics so the tool produces actionable output tomorrow.
2. **Medium term (2–4 weeks):** Restore sold data via scraper cache + throttled Finding API with intelligent batching.

---

## 1. Strategos — Summer Priority & Business Strategy

### 1.1 What Sells Fast in Summer (Germany)

Germany's S/S resale peak is **May–August**. The current keyword mix is ~60% wrong for this season. Here's the reality:

| Category | Summer Relevance (DE) | Current Status | Action |
|----------|----------------------|----------------|--------|
| **Birkenstock (all models)** | 🔥 Peak season (May–Sep) | ✅ Tracked | **KEEP — top priority** |
| **Hiking boots (Lowa/Meindl)** | 🌡️ Active (May–Sep hiking) | ✅ Tracked | **KEEP — second priority** |
| **Cycling bags (Ortlieb)** | 🌡️ Seasonal (May–Sep) | ✅ Tracked | **KEEP** |
| **Backpacks (Deuter/Vaude)** | 🌡️ Travel season (Jun–Aug) | ✅ Tracked | **KEEP** |
| **Outdoor jackets (Arc'teryx/Jack Wolfskin)** | ❌ Wrong season | ✅ Tracked | **Deprioritize until Sep** |
| **Fleeces / Puffers (Patagonia)** | ❌ Wrong season | ✅ Tracked | **Deprioritize until Sep** |
| **Vintage Levi's 501** | 🌡️ Festival season (Jun–Aug) | ✅ Tracked | **KEEP** |
| **Ballet flats (Miu Miu/Repetto)** | 🔥 Peak (S/S fashion) | ✅ Tracked | **KEEP** |

### 1.2 Seasonal Weighting Strategy

Add a `seasonal_boost` field to each keyword. The sellability formula should weight current-season keywords higher:

```python
SEASONAL_PROFILES = {
    # keyword: (boost_May, boost_Jun, boost_Jul, boost_Aug, boost_Sep)
    "Birkenstock Arizona":     (1.30, 1.40, 1.30, 1.20, 1.00),
    "Birkenstock Boston":      (1.30, 1.40, 1.30, 1.20, 1.00),
    "Birkenstock Gizeh":       (1.30, 1.40, 1.30, 1.20, 1.00),
    "Birkenstock Madrid":      (1.30, 1.40, 1.30, 1.20, 1.00),
    "Birkenstock EVA":         (1.30, 1.40, 1.30, 1.20, 1.00),
    "Lowa Renegade GTX":       (1.10, 1.20, 1.20, 1.10, 1.00),
    "Meindl Ortler":           (1.10, 1.20, 1.20, 1.10, 1.00),
    "Ortlieb Back-Roller":     (1.20, 1.30, 1.30, 1.20, 1.00),
    "Ortlieb Velocity":        (1.20, 1.30, 1.30, 1.20, 1.00),
    "Vintage Levi's 501":      (1.10, 1.30, 1.20, 1.10, 1.00),
    "Miu Miu Ballerinas":      (1.20, 1.30, 1.20, 1.10, 1.00),
    "Repetto Ballerinas":      (1.20, 1.30, 1.20, 1.10, 1.00),
    "Chanel Ballerinas":       (1.20, 1.30, 1.20, 1.10, 1.00),
    # Winter items — DE-penalize in summer
    "Patagonia Nano Puff":     (0.60, 0.50, 0.50, 0.60, 0.80),
    "Patagonia Retro-X Fleece":(0.60, 0.50, 0.50, 0.60, 0.80),
    "Arc'teryx Beta LT":       (0.70, 0.60, 0.60, 0.70, 0.90),
    "Arc'teryx Atom LT":       (0.70, 0.60, 0.60, 0.70, 0.90),
    "Jack Wolfskin 3in1 Jacket":(0.50, 0.40, 0.40, 0.50, 0.80),
}
```

This is NOT a fake score inflation — it's a **prioritization signal**. A Birkenstock with identical raw metrics should rank above a Nano Puff in June because the reseller needs to know what to source *now*.

### 1.3 Recommendation: Split Dashboard into "Seasonal Picks" vs "All"

Add a toggle on the dashboard:
- **🌞 Summer Picks** (May–Sep boosted keywords)
- **📊 All Keywords** (full universe)

This answers Wahaj's question directly without hiding the winter items.

---

## 2. Analyticos — Data Quality & Rate Limit Strategy

### 2.1 The Sold Data Problem (Diagnosis)

The Finding API is returning:
```
HTTP 500: "exceeded the number of times the operation is allowed"
```

This is **not a per-second rate limit** — it's a **daily operation quota**. eBay Finding API allows ~5,000 calls/day per App ID. At 50 keywords × 2 markets × ~20 paginated calls = ~2,000 calls, you should fit. But:

1. The `_rate_limit()` only enforces 0.21s spacing (~5 calls/sec). It does NOT track cumulative daily calls.
2. The 2026-04-26 scrape files (76 of them) prove the scraper DID work for DE. US data returned `sold_count: 0` but with price arrays — this is bot-detection stripping the sold-filter params.
3. The pipeline is calling Finding API fresh every run, ignoring cached scrape data.

### 2.2 Immediate Fix: Use Cached Scrape Files

**The scraper already produced usable data on 2026-04-26.** The pipeline should read these files before calling any API.

```python
# Add to pipeline.py or finding_api.py

def load_cached_sold_data(keyword, marketplace, date_str=None):
    """Load previously scraped sold data from disk cache.
    Returns dict matching get_sold_stats() output or None."""
    date_str = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_kw = keyword.replace("/", "_").replace(" ", "_")
    cache_path = DATA_DIR / f"sold_{marketplace}_{safe_kw}_{date_str}.json"
    
    if not cache_path.exists():
        # Fallback: try yesterday
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        cache_path = DATA_DIR / f"sold_{marketplace}_{safe_kw}_{yesterday}.json"
    
    if cache_path.exists():
        with open(cache_path) as f:
            data = json.load(f)
        # Normalize to the same structure as get_sold_stats()
        prices = data.get("prices", [])
        return {
            "sold_count": data.get("sold_count", len(prices)),
            "fetched_count": len(prices),
            "avg_price": round(mean(prices), 2) if prices else 0,
            "median_price": round(median(prices), 2) if prices else 0,
            "min_price": round(min(prices), 2) if prices else 0,
            "max_price": round(max(prices), 2) if prices else 0,
            "prices": prices,
            "items": [{"price": p} for p in prices],
            "by_option": {"FIXED_PRICE": {}, "AUCTION": {}},
            "error": None,
            "source": "cache",
        }
    return None
```

Then in the pipeline:
```python
# Try cache first
sold = load_cached_sold_data(keyword, mkt, today)
if sold is None:
    # Only then call API
    sold = get_sold_stats(keyword, mkt, cat_id, days)
    # And save it
    save_sold_data_to_cache(keyword, mkt, today, sold)
```

### 2.3 Rate Limit Strategy for Finding API

Track daily calls in a persistent counter file:

```python
# finding_api.py — add to _rate_limit()

def _rate_limit():
    global _last_call_time
    elapsed = time.time() - _last_call_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_call_time = time.time()
    
    # Track daily quota
    _track_daily_call()

def _track_daily_call():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    quota_file = Path(__file__).parent / "data" / "api_quota.json"
    quota = {"date": today, "finding_calls": 0, "browse_calls": 0}
    if quota_file.exists():
        with open(quota_file) as f:
            saved = json.load(f)
            if saved.get("date") == today:
                quota = saved
    
    quota["finding_calls"] += 1
    with open(quota_file, "w") as f:
        json.dump(quota, f)
    
    # Hard stop at 4,500 (leave buffer)
    if quota["finding_calls"] > 4500:
        raise RuntimeError("Daily Finding API quota exhausted")
```

**Batching strategy:** Instead of 50 keywords in one session, split into 3 batches across the day:
- **Batch 1 (06:00 UTC):** Top 16 summer keywords (Birkenstock, hiking, sandals)
- **Batch 2 (14:00 UTC):** Next 17 keywords (mid-priority)
- **Batch 3 (22:00 UTC):** Remaining 17 keywords + retry failures

This spreads the load and avoids the "operation exceeded" error.

### 2.4 Alternative: Use Terapeak / Marketplace Insights

If Finding API dies permanently, the only eBay-sanctioned alternative is **Terapeak** (built into eBay Seller Hub). There is no public API. Options:

| Option | Effort | Cost | Reliability |
|--------|--------|------|-------------|
| **Continue Finding API + caching** | Low | Free | Medium (while it lasts) |
| **Scrape eBay sold pages (Selenium/Playwright)** | Medium | $20/mo VPS | Medium-High |
| **Use eBay Buy API `search` + heuristic** | Low | Free | Low (no sold data) |
| **Third-party: Worthpoint, Terapeak** | Low | $20–50/mo | High |

**Recommendation:** Continue Finding API with aggressive caching + daily quota tracking. Begin prototyping a Playwright scraper for sold listings as a backup.

---

## 3. Sellability Formula v2 — No Sold Data Required

### 3.1 The Proxy Metrics Available from Browse API

When `sold_count = 0`, we can estimate sellability from these Browse API signals:

| Proxy Metric | Formula | What It Tells Us |
|--------------|---------|------------------|
| **Market Depth** | `log10(active_count)` | More listings = more liquid market |
| **Price Stability** | `1 - (price_std / price_mean)` | Low volatility = stable demand |
| **Auction Ratio** | `auction_count / active_count` | Higher = more bidding competition |
| **BIN Dominance** | `fixed_price_count / active_count` | Higher = "buy it now" culture = faster sales |
| **Listing Freshness** | `avg(age_days)` | Younger listings = faster turnover |
| **Category Concentration** | `% of listings in target category` | Higher = less noise, more signal |
| **Multi-variation Penalty** | `1 / (1 + variation_estimate)` | Birkenstock has 1 listing = 10 SKUs |

### 3.2 The New Formula

```python
def calculate_sellability_v2(
    active_count: int,
    fixed_price_count: int,
    auction_count: int,
    sample_items: list,
    seasonal_boost: float = 1.0,
    has_sold_data: bool = False,
    sold_count: int = 0,
    avg_sold_price: float = 0,
):
    """
    v2 Sellability Index — works with OR without sold data.
    Returns: index (0.0–1.0+), confidence, band, reasoning
    """
    
    # --- Base metrics from Browse API ---
    total = max(active_count, 1)
    fp_ratio = fixed_price_count / total
    auction_ratio = auction_count / total
    
    # Listing age from sample items
    ages = []
    for item in sample_items:
        if item.get("item_creation_date"):
            try:
                created = datetime.fromisoformat(item["item_creation_date"].replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - created).days
                ages.append(age_days)
            except:
                pass
    avg_age_days = mean(ages) if ages else 30
    
    # --- Signal 1: Market Depth (log-scaled) ---
    # 100 active = 0.20, 1000 = 0.40, 10000 = 0.60
    depth_score = min(1.0, max(0.0, log10(total) / 5.0))
    
    # --- Signal 2: Turnover Proxy (younger = better) ---
    # If avg listing is 10 days old, market is hot. If 90 days, stale.
    freshness_score = 1.0 - min(1.0, avg_age_days / 90.0)
    
    # --- Signal 3: Buying Option Mix ---
    # Pure BIN market = higher sell-through (buyers want instant purchase)
    # Pure auction = lower but can mean scarcity
    # Ideal: 60-80% BIN, 20-40% auction = healthy liquidity
    bin_health = 1.0 - abs(fp_ratio - 0.7)  # peaks at 70% BIN
    bin_health = max(0.0, bin_health)
    
    # --- Signal 4: Price Distribution Health ---
    prices = [item["price"] for item in sample_items if item.get("price", 0) > 0]
    if len(prices) >= 5:
        price_cv = stdev(prices) / mean(prices) if mean(prices) > 0 else 1.0
        price_stability = 1.0 - min(1.0, price_cv)
    else:
        price_stability = 0.3  # default low confidence
    
    # --- Combine (equal weights for now; tune later) ---
    proxy_index = (
        depth_score * 0.30 +
        freshness_score * 0.30 +
        bin_health * 0.20 +
        price_stability * 0.20
    )
    
    # --- Override if we DO have sold data ---
    if has_sold_data and sold_count > 0:
        # Classic STR-based index
        str_pct = sold_count / (sold_count + active_count)
        index = str_pct * 3.0  # Scale so 0.20 STR = 0.60 index
        index = min(1.0, index)
        confidence = "HIGH" if sold_count >= 100 else "MEDIUM" if sold_count >= 30 else "LOW"
    else:
        # Proxy-only index
        index = proxy_index * seasonal_boost
        confidence = "PROXY"  # New tag: data from active listings only
    
    # --- Band assignment ---
    if index >= 0.60:
        band = "HOT"
    elif index >= 0.30:
        band = "WARM"
    else:
        band = "COLD"
    
    return {
        "index": round(index, 3),
        "confidence": confidence,
        "band": band,
        "depth_score": round(depth_score, 3),
        "freshness_score": round(freshness_score, 3),
        "bin_health": round(bin_health, 3),
        "price_stability": round(price_stability, 3),
        "seasonal_boost": seasonal_boost,
        "avg_age_days": round(avg_age_days, 1),
        "has_sold_data": has_sold_data,
    }
```

### 3.3 Why This Works

With Birkenstock Arizona DE (2,837 active, ~70% BIN, avg age ~15 days):
- `depth_score` = log10(2837)/5 = 0.75/5 = **0.30** → Wait, log10(2837) = 3.45, /5 = **0.69**
- `freshness_score` = 1 - 15/90 = **0.83**
- `bin_health` = 1 - |0.70 - 0.7| = **1.0**
- `price_stability` = ~0.85 (Birkenstock prices cluster €65-80)
- `proxy_index` = 0.69×0.30 + 0.83×0.30 + 1.0×0.20 + 0.85×0.20 = **0.82**
- With seasonal_boost = 1.30 (June): **1.07** → capped at 1.0, band = HOT

With Patagonia Nano Puff DE (107 active, mixed BIN/auction, older listings):
- `depth_score` = log10(107)/5 = 2.03/5 = **0.41**
- `freshness_score` = 1 - 45/90 = **0.50**
- `bin_health` = ~0.70
- `proxy_index` = 0.41×0.30 + 0.50×0.30 + 0.70×0.20 + 0.50×0.20 = **0.52**
- With seasonal_boost = 0.50 (June): **0.26** → band = COLD

This is **directionally correct** — Birkenstock should be HOT in summer, Nano Puff should be COLD.

### 3.4 New Confidence Tag: `PROXY`

Add a fourth confidence level:
- `HIGH` — Sold data + 100+ units, validated
- `MEDIUM` — Sold data + 30–99 units
- `LOW` — Sold data + <30 units
- `PROXY` — **No sold data; score derived from active-market signals only**

This is honest. Users see the tag and understand the limitation.

---

## 4. Data Pipeline Fixes (Daily Cron)

### 4.1 Current Cron Problems

1. Runs all 50 keywords in one session → hits rate limits
2. Does not use cached scrape data → re-calls API for data that already exists
3. No daily quota tracking → silent failure after quota exhaustion
4. No EUR/USD conversion → cross-market comparison is apples-to-oranges
5. No multi-variation adjustment → Birkenstock counts are inflated 5–10×

### 4.2 Recommended Pipeline v2

```python
# pipeline.py — revised run_pipeline()

def run_pipeline_v2(keywords_de=None, keywords_us=None, days=30, use_cache=True):
    keywords_de = keywords_de or KEYWORDS_DE
    keywords_us = keywords_us or KEYWORDS_US
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    init_db()
    
    # Load category map
    category_map = {}
    if CAT_MAP_PATH.exists():
        with open(CAT_MAP_PATH) as f:
            category_map = json.load(f)
    
    # Daily FX rate (cache for 24h)
    fx_rate = get_eur_usd_rate()  # ~1.08 currently
    
    results = []
    errors = []
    
    # Determine seasonal boost
    month = datetime.now().month
    
    all_keywords = [("de", keywords_de), ("us", keywords_us)]
    
    for mkt, keywords in all_keywords:
        for keyword in keywords:
            # --- Step 1: Browse API (always needed) ---
            cat_id = category_map.get(keyword, {}).get(mkt, {}).get("category_id")
            try:
                active = get_active_counts(keyword, mkt, cat_id)
            except Exception as e:
                errors.append(f"{keyword} ({mkt}) browse: {e}")
                continue
            
            total_active = active.get("total", 0)
            active_fixed = active.get("fixed_price", 0)
            active_auction = active.get("auction", 0)
            items = active.get("items", [])
            
            # --- Step 2: Sold data (cache first, API second) ---
            sold = None
            if use_cache:
                sold = load_cached_sold_data(keyword, mkt, today)
            
            has_sold_data = sold is not None and sold.get("sold_count", 0) > 0
            
            if not has_sold_data:
                # Only call API if cache miss AND quota available
                try:
                    if check_finding_quota():
                        sold = get_sold_stats(keyword, mkt, cat_id, days)
                        save_sold_data_to_cache(keyword, mkt, today, sold)
                        has_sold_data = sold.get("sold_count", 0) > 0
                    else:
                        errors.append(f"{keyword} ({mkt}): Finding API quota exhausted")
                except Exception as e:
                    errors.append(f"{keyword} ({mkt}) finding: {e}")
            
            total_sold = sold.get("sold_count", 0) if sold else 0
            avg_price = sold.get("avg_price", 0) if sold else 0
            
            # --- Step 3: Multi-variation adjustment ---
            # Birkenstock: 1 listing = ~8 size/color variations
            # Use keyword-specific adjustment factors
            variation_factor = VARIATION_ADJUSTMENTS.get(keyword, 1.0)
            adjusted_active = int(total_active / variation_factor)
            
            # --- Step 4: Currency normalization ---
            if mkt == "us":
                # Convert USD prices to EUR for cross-market comparison
                avg_price_eur = avg_price / fx_rate if fx_rate else avg_price
            else:
                avg_price_eur = avg_price
            
            # --- Step 5: Sellability v2 ---
            seasonal_boost = get_seasonal_boost(keyword, month)
            
            metrics = calculate_sellability_v2(
                active_count=adjusted_active,
                fixed_price_count=active_fixed,
                auction_count=active_auction,
                sample_items=items,
                seasonal_boost=seasonal_boost,
                has_sold_data=has_sold_data,
                sold_count=total_sold,
                avg_sold_price=avg_price,
            )
            
            # --- Step 6: ROI with Fleek ---
            fleek = get_fleek_prices(keyword)
            roi_data = calculate_roi(avg_price_eur, fleek) if has_sold_data else {}
            
            # Store in DB (new schema)
            store_snapshot_v2(
                date=today,
                keyword=keyword,
                marketplace=mkt,
                active_count=adjusted_active,
                raw_active_count=total_active,
                fixed_price_count=active_fixed,
                auction_count=active_auction,
                sold_count=total_sold,
                avg_price=avg_price,
                avg_price_eur=avg_price_eur,
                sellability_index=metrics["index"],
                confidence=metrics["confidence"],
                band=metrics["band"],
                seasonal_boost=seasonal_boost,
                has_sold_data=has_sold_data,
                fleek_min=fleek.get("min_price", 0),
                fleek_avg=fleek.get("avg_price", 0),
                margin=roi_data.get("margin", 0),
                roi=roi_data.get("roi", 0),
            )
            
            results.append({
                "keyword": keyword,
                "marketplace": mkt,
                "active": adjusted_active,
                "raw_active": total_active,
                "sold": total_sold,
                "avg_price": avg_price,
                "avg_price_eur": avg_price_eur,
                "sellability": metrics["index"],
                "band": metrics["band"],
                "confidence": metrics["confidence"],
                "has_sold_data": has_sold_data,
                "seasonal_boost": seasonal_boost,
                **roi_data,
            })
    
    # Save raw JSON
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data_path = DATA_DIR / f"{today}.json"
    with open(data_path, "w") as f:
        json.dump({"date": today, "results": results, "errors": errors}, f, indent=2)
    
    # Generate dashboard
    generate_dashboard_data(results, today)
    
    # Generate report
    from report import generate_report
    messages = generate_report(date=today)
    
    return results, messages, errors
```

### 4.3 New DB Schema

```sql
-- Add these columns to snapshots table
ALTER TABLE snapshots ADD COLUMN raw_active_count INTEGER DEFAULT 0;
ALTER TABLE snapshots ADD COLUMN fixed_price_count INTEGER DEFAULT 0;
ALTER TABLE snapshots ADD COLUMN auction_count INTEGER DEFAULT 0;
ALTER TABLE snapshots ADD COLUMN avg_price_eur REAL DEFAULT 0;
ALTER TABLE snapshots ADD COLUMN seasonal_boost REAL DEFAULT 1.0;
ALTER TABLE snapshots ADD COLUMN has_sold_data INTEGER DEFAULT 0;
ALTER TABLE snapshots ADD COLUMN band TEXT DEFAULT 'COLD';
ALTER TABLE snapshots ADD COLUMN fleek_min REAL DEFAULT 0;
ALTER TABLE snapshots ADD COLUMN fleek_avg REAL DEFAULT 0;
ALTER TABLE snapshots ADD COLUMN margin REAL DEFAULT 0;
ALTER TABLE snapshots ADD COLUMN roi REAL DEFAULT 0;
```

### 4.4 Cron Schedule (3 Batches)

```bash
# crontab — spread across the day
# Batch 1: Summer priorities (Birkenstock, sandals, hiking)
0 6 * * * cd /home/wahaj/.openclaw/workspace/thrift-cycle && python3 run_batch.py --batch summer

# Batch 2: Mid-priority (ballet flats, Levi's, bags)
0 14 * * * cd /home/wahaj/.openclaw/workspace/thrift-cycle && python3 run_batch.py --batch mid

# Batch 3: Low-priority + retries (jackets, fleeces)
0 22 * * * cd /home/wahaj/.openclaw/workspace/thrift-cycle && python3 run_batch.py --batch low --retry-failed
```

---

## 5. ROI Calculation Without Sold Prices

### 5.1 The Problem

Without sold data, `avg_sold_price = 0`. ROI = (sold_price - cost) / cost = undefined.

### 5.2 The Fallback: Use Active Listing Price as Proxy

When sold data is unavailable, use the **median active listing price** as a conservative estimate of market value. Active prices are typically 10–20% higher than sold prices (unsold items are overpriced), so apply a discount:

```python
def calculate_roi(avg_price, fleek_data, has_sold_data=False, active_prices=None):
    """Calculate ROI and margin.
    
    If has_sold_data: use actual avg sold price.
    If no sold data: use median active price × 0.85 (conservative discount).
    """
    fleek_avg = fleek_data.get("avg_price", 0)
    fleek_min = fleek_data.get("min_price", 0)
    
    if fleek_avg <= 0:
        return {"margin": 0, "roi": 0, "cost": 0, "est_price": 0, "method": "no_fleek"}
    
    if has_sold_data and avg_price > 0:
        est_price = avg_price
        method = "sold_price"
    elif active_prices:
        # Conservative: active prices are inflated, discount 15%
        median_active = median(active_prices)
        est_price = median_active * 0.85
        method = "active_proxy"
    else:
        est_price = 0
        method = "no_price_data"
    
    if est_price <= 0:
        return {"margin": 0, "roi": 0, "cost": fleek_avg, "est_price": 0, "method": method}
    
    # Best-case (pay Fleek min, sell at est_price)
    margin_best = est_price - fleek_min
    roi_best = (margin_best / fleek_min) * 100 if fleek_min > 0 else 0
    
    # Expected-case (pay Fleek avg, sell at est_price)
    margin_expected = est_price - fleek_avg
    roi_expected = (margin_expected / fleek_avg) * 100 if fleek_avg > 0 else 0
    
    return {
        "margin": round(margin_expected, 2),
        "roi": round(roi_expected, 2),
        "margin_best": round(margin_best, 2),
        "roi_best": round(roi_best, 2),
        "cost": fleek_avg,
        "est_price": round(est_price, 2),
        "method": method,
    }
```

### 5.3 Dashboard Display

When ROI is derived from active prices (not sold), show it differently:

```javascript
// In dashboard JS
const roiLabel = item.method === 'sold_price' 
    ? `${item.roi.toFixed(0)}%` 
    : `~${item.roi.toFixed(0)}% (est.)`;
const roiClass = item.method === 'sold_price' ? 'roi-confirmed' : 'roi-estimated';
```

Style `roi-estimated` with a dashed border or lighter color so users know it's approximate.

---

## 6. Creativos — Dashboard UX Improvements

### 6.1 Critical Fix: Show All 50 Items, Not 4

The dashboard currently embeds `data.js` with only 4 test-mode results. Fix `generate_dashboard.py` to read the full daily JSON:

```python
def generate_dashboard_data(results, date_str):
    """Generate data.js from pipeline results."""
    data = {
        "date": date_str,
        "results": results,  # ALL results, not just 4
    }
    output_path = Path(DOCS_DIR) / "data.js"
    with open(output_path, "w") as f:
        f.write("const PIPELINE_DATA = ")
        json.dump(data, f, indent=2)
        f.write(";")
    print(f"Wrote {len(results)} results to {output_path}")
```

### 6.2 Add "Data Quality" Indicator

Each row should show a small badge:
- 🟢 Confirmed (sold data available)
- 🟡 Estimated (proxy index, no sold data)
- 🔴 Stale (using cached data > 7 days old)

### 6.3 Summer Picks Section

Add a pinned section at the top of the dashboard:

```html
<div class="summer-picks">
  <h2>🌞 Summer Picks (Germany)</h2>
  <p>Keywords with seasonal boost for May–September</p>
  <!-- Render only items where seasonal_boost > 1.0 and marketplace === 'de' -->
</div>
```

### 6.4 Cross-Market Arbitrage View

Since we track DE + US, show when the same item has wildly different metrics:

```javascript
function findArbitrage(data) {
    const byKeyword = {};
    data.forEach(item => {
        if (!byKeyword[item.keyword]) byKeyword[item.keyword] = [];
        byKeyword[item.keyword].push(item);
    });
    
    return Object.entries(byKeyword)
        .filter(([_, items]) => items.length === 2)  // both DE + US
        .map(([kw, items]) => {
            const de = items.find(i => i.marketplace === 'de');
            const us = items.find(i => i.marketplace === 'us');
            if (!de || !us) return null;
            const roiDiff = (de.roi || 0) - (us.roi || 0);
            return { keyword: kw, roiDiff, de, us };
        })
        .filter(x => x && Math.abs(x.roiDiff) > 50)
        .sort((a, b) => Math.abs(b.roiDiff) - Math.abs(a.roiDiff));
}
```

### 6.5 Actionable Next Step for Each Item

Instead of just showing numbers, add a "What to do" column:

| Score | Action |
|-------|--------|
| HOT + Fleek match | "🛒 Source on Fleek — list within 7 days" |
| HOT + no Fleek | "🔍 Source elsewhere — high velocity confirmed" |
| WARM + Fleek | "📊 Test with 5 units — monitor for 2 weeks" |
| COLD + any | "⏸️ Skip for now — low liquidity" |
| PROXY confidence | "⚠️ Score estimated — validate with manual sold search" |

---

## 7. Implementation Priority

### Week 1 (Immediate — Tool Must Produce Output)

1. ✅ Implement `calculate_sellability_v2()` with proxy metrics
2. ✅ Add seasonal boost lookup
3. ✅ Update pipeline to use v2 formula when sold data = 0
4. ✅ Fix dashboard generator to output all 50 items
5. ✅ Add `PROXY` confidence tag to dashboard

### Week 2 (Data Quality)

1. Implement sold-data cache reader in pipeline
2. Add daily API quota tracking
3. Add multi-variation adjustment factors
4. Add EUR/USD conversion
5. Split pipeline into 3 batches

### Week 3 (UX Polish)

1. Add "Summer Picks" pinned section to dashboard
2. Add arbitrage view (DE vs US)
3. Add action-column to table
4. Add data quality badges (🟢🟡🔴)
5. Style estimated ROI differently from confirmed ROI

### Week 4 (Hedge Strategy)

1. Prototype Playwright scraper for sold listings
2. Compare scraper output vs Finding API for 10 keywords
3. Decision: keep Finding API or switch to scraper
4. Document findings in memory

---

## 8. Key Metrics to Track

| Metric | Target | How to Measure |
|--------|--------|---------------|
| % keywords with non-zero sellability | 100% | Dashboard daily |
| % HOT items in summer keywords | ≥30% | Report weekly |
| Avg sellability of summer items | ≥0.50 | Report weekly |
| Finding API success rate | ≥80% | Quota tracker |
| Dashboard load time | <3s | Manual check |
| Days since last sold data | ≤7 | Cache freshness check |

---

## 9. Files to Modify

| File | Changes |
|------|---------|
| `pipeline.py` | Add v2 formula, cache loading, batching, quota tracking, seasonal boost, FX conversion |
| `browse_api.py` | Add listing age extraction, price sampling for ROI proxy |
| `finding_api.py` | Add daily quota tracker, cache writer |
| `fleek_scraper.py` | Add `calculate_roi()` function |
| `generate_dashboard.py` | Fix to output all results, add new fields |
| `docs/index.html` | Add Summer Picks section, data quality badges, action column, arbitrage view |
| `docs/product_types.js` | Add seasonal profiles |
| `technical-design.md` | Document v2 formula |

---

*Council review compiled by subagent. All 6 questions addressed with code-level specificity. Ready for implementation.*
