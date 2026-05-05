# Thrift-Cycle Pipeline Fix — 2026-05-02

## Problems Identified
1. **Pipeline timeouts/SIGKILLs**: Rate limiting on eBay Finding API causes exponential backoff retries (2s, 4s, 8s per call). With 50 keywords and 1.0s base interval, pipeline runs too long and gets killed.
2. **No data for 2026-05-02**: Pipeline was SIGKILLed before completion. No daily JSON produced.
3. **Zero sellability on 2026-05-01**: All entries show `sellability: 0.0` and `confidence: LOW` despite having sold counts (e.g., 20 sold / 295 active). This is mathematically wrong — index should be ~0.03, not 0.0.
4. **No cron job**: Pipeline only runs manually. Needs a daily cron.

## Fixes Required

### 1. finding_api.py — Rate Limit Handling
- Increase `_MIN_INTERVAL` from 1.0s to 2.5s (safer for eBay's burst limits)
- Reduce `_MAX_RETRIES` from 3 to 2 (avoid excessive delays)
- Add early-exit: if rate limited on a keyword, skip remaining pages and return what we have
- Add a daily call budget: stop after ~200 Finding API calls to guarantee completion

### 2. pipeline.py — Smarter Execution
- Add `--fast` mode that processes only top 10 keywords per market (high-priority items)
- Add `--market` flag to run only DE or US (for partial recovery runs)
- Reduce default keyword list to top 15 per market for daily runs
- Add timeout safety: catch SIGALRM or use a max-runtime limit
- Fix the sellability=0.0 bug — investigate why calculate_metrics returns 0.0

### 3. Calculate Metrics Bug
Looking at the code:
```python
index_raw = (sold_count / active_count) if active_count > 0 else 0.0
```
For 20/295 = 0.068. Then:
```python
multiplier = min(1.0, sold_count / 30)  # 20/30 = 0.667
listing_age_penalty = 1.0 - min(1.0, avg_listing_age_days / 90)  # 1.0 - 0.333 = 0.667
index_final = index_raw * multiplier * listing_age_penalty  # 0.068 * 0.667 * 0.667 = 0.030
```
But the JSON shows 0.0. This suggests the `sold_count` passed to `calculate_metrics` is actually 0, not 20. Check if `by_option` or `all` path is passing wrong values.

Actually looking more carefully at the pipeline code:
```python
for option in ["all"] + BUYING_OPTIONS:
    if option == "all":
        option_active = total_active
        option_sold = total_sold
        option_avg = avg_price
    else:
        ...

    metrics = calculate_metrics(option_sold, option_active)
    ...
    index_final = metrics["index_final"]
    
    if option == "all":
        results.append({
            "sellability": index_final,
            ...
        })
```

The issue might be that `total_sold` is 0 when the API returns an error and cached data is used. Check the fallback cache — the cached data might have `sold_count: 0`.

### 4. Cron Setup
- Add a cron job: `0 6 * * * cd /home/wahaj/.openclaw/workspace/thrift-cycle && timeout 600 python3 pipeline.py --fast >> /home/wahaj/.openclaw/workspace/thrift-cycle/cron.log 2>&1`
- The `timeout 600` ensures it can't hang forever

### 5. Test Run
After fixes, run: `python3 pipeline.py --test` to verify it completes without errors and produces non-zero sellability for items with sales.

## Files to Modify
- `/home/wahaj/.openclaw/workspace/thrift-cycle/finding_api.py`
- `/home/wahaj/.openclaw/workspace/thrift-cycle/pipeline.py`
- `/home/wahaj/.openclaw/workspace/thrift-cycle/quota_tracker.py` (add daily budget)

## Deliverables
1. Modified files with fixes applied
2. Test run output showing success
3. Cron job installed and verified
4. Brief summary of what was changed and why
