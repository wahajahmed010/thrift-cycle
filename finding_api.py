#!/usr/bin/env python3
"""eBay Sold Data — Fetches completed/sold listing data for Thrift-Cycle.
Since the Finding API's findCompletedItems is deprecated (returns 404),
this module uses the Browse API with SOLD filter and web scraping as fallback.

Strategy:
1. Try Browse API with sold-related filters first
2. Fall back to scraping eBay's public sold listings page
3. Cache results to minimize API/scrape calls
"""

import json
import time
import urllib.request
import urllib.parse
import re
import sys
import os
from datetime import datetime, timedelta, timezone
from statistics import mean, median

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ebay_auth import get_token

BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
EBAY_SOLD_URL_DE = "https://www.ebay.de/sch/i.html?LH_Sold=1&LH_Complete=1&_nkw="
EBAY_SOLD_URL_US = "https://www.ebay.com/sch/i.html?LH_Sold=1&LH_Complete=1&_nkw="

MARKETPLACES = {
    "de": "EBAY-DE",
    "us": "EBAY-US",
}

SOLD_URLS = {
    "de": EBAY_SOLD_URL_DE,
    "us": EBAY_SOLD_URL_US,
}

RATE_LIMIT_DELAY = 0.3
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

def try_browse_api_sold(keyword, marketplace="EBAY-US", category_id=None, days=30):
    """Try to get sold data via Browse API.
    Note: Browse API doesn't natively support sold/completed items.
    This function attempts various filter combinations.
    """
    token = get_token()
    
    # The Browse API doesn't have a direct "sold" filter, but we can try
    # condition=USED and check itemEndDate to infer sold status
    params = {
        "q": keyword,
        "marketplace_ids": marketplace,
        "limit": "50",
        "filter": "conditions:{USED}",
    }
    if category_id:
        params["category_ids"] = str(category_id)
    
    url = f"{BROWSE_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-EBAY-C-MARKETPLACE-ID": marketplace,
    })
    
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"sold_count": 0, "prices": [], "error": str(e.code)}
    
    # This gives us active used listings, not sold
    # We need sold data from elsewhere
    items = data.get("itemSummaries", [])
    prices = []
    for item in items:
        price = item.get("price", {})
        if price and "value" in price:
            prices.append(float(price["value"]))
    
    return {
        "sold_count": 0,  # Browse API can't give us this
        "active_used_count": data.get("total", 0),
        "prices": prices,
        "avg_price": round(mean(prices), 2) if prices else 0,
        "median_price": round(median(prices), 2) if prices else 0,
        "source": "browse_api_active",
    }

def scrape_sold_listings(keyword, marketplace="us", days=30):
    """Scrape sold listings from eBay's public search page.
    
    This is the fallback since the API doesn't support sold data.
    Returns approximate sold count and prices.
    """
    base_url = SOLD_URLS.get(marketplace, SOLD_URLS["us"])
    query = urllib.parse.quote(keyword)
    url = f"{base_url}{query}&_dcat=0"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"  Scrape error ({e.code})", file=sys.stderr)
        return {"sold_count": 0, "prices": [], "source": "scrape_failed", "error": str(e.code)}
    except Exception as e:
        print(f"  Scrape error: {e}", file=sys.stderr)
        return {"sold_count": 0, "prices": [], "source": "scrape_failed", "error": str(e)}
    
    # Parse total results count
    # eBay's sold page is JS-rendered — total count is hard to extract from raw HTML.
    # Try JSON in script tags first, then plain text patterns.
    # Fallback: estimate from price samples found (each price = 1 sold listing minimum)
    total_match = re.search(r'"totalItems"\s*:\s*"?(\d+)"?', html)
    if not total_match:
        total_match = re.search(r'(\d[\d,.]+)\s*(?:results?|Ergebnisse?|items?|listings?)', html, re.IGNORECASE)
    sold_count = 0
    if total_match:
        try:
            sold_count = int(total_match.group(1).replace(",", "").replace(".", ""))
        except ValueError:
            sold_count = 0
    
    # Parse sold prices from listing page
    # Match currency symbols followed by price amounts
    usd_or_eur = r'(?:' + re.escape('$') + r'|\u20ac|EUR\s?)'
    price_pattern = re.findall(usd_or_eur + r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2}))', html)
    prices = []
    for p in price_pattern[:100]:  # Limit to 100 prices
        try:
            price = float(p.replace(",", ".") if marketplace == "de" else p.replace(",", ""))
            if 1 <= price <= 10000:  # Reasonable price range
                prices.append(price)
        except ValueError:
            continue
    
    # Fallback: if we couldn't parse the count but found prices, estimate from sample
    if sold_count == 0 and len(prices) > 0:
        sold_count = len(prices)  # Minimum: we found this many sold listings
        source_note = "estimated_from_samples"
    else:
        source_note = "scrape"
    
    return {
        "sold_count": sold_count,
        "prices": prices,
        "avg_price": round(mean(prices), 2) if prices else 0,
        "median_price": round(median(prices), 2) if prices else 0,
        "min_price": round(min(prices), 2) if prices else 0,
        "max_price": round(max(prices), 2) if prices else 0,
        "sample_size": len(prices),
        "source": source_note,
    }

def get_sold_stats(keyword, marketplace="us", category_id=None, days=30, use_cache=True):
    """Get sold statistics for a keyword.
    
    Strategy:
    1. Check cache first
    2. Try Browse API for active used prices
    3. Scrape sold listings page for count and price data
    4. Cache results
    """
    # Check cache
    os.makedirs(CACHE_DIR, exist_ok=True)
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    cache_file = os.path.join(CACHE_DIR, f"sold_{marketplace}_{keyword.replace(' ', '_').replace('/', '_')}_{today}.json")
    
    if use_cache and os.path.exists(cache_file):
        with open(cache_file) as f:
            cached = json.load(f)
            if cached.get("date") == today:
                print(f"  (cached) {keyword} ({marketplace})", end=" ", flush=True)
                return cached
    
    mp = MARKETPLACES.get(marketplace, marketplace)
    
    # Try scraping sold listings (most reliable source for sold data)
    print(f"  Scraping sold: '{keyword}' ({mp})...", end=" ", flush=True)
    result = scrape_sold_listings(keyword, marketplace, days)
    time.sleep(RATE_LIMIT_DELAY)
    
    # Also get active used prices from Browse API for comparison
    browse_result = try_browse_api_sold(keyword, mp, category_id)
    result["active_used_count"] = browse_result.get("active_used_count", 0)
    result["active_used_avg_price"] = browse_result.get("avg_price", 0)
    
    result["keyword"] = keyword
    result["marketplace"] = marketplace
    result["date"] = today
    
    # Cache
    with open(cache_file, "w") as f:
        json.dump(result, f, indent=2)
    
    print(f"sold={result.get('sold_count', 0)}, avg=${result.get('avg_price', 0)}, src={result.get('source', '?')}")
    return result

def batch_sold_stats(keywords, category_map=None, marketplaces=("de", "us"), days=30):
    """Calculate sold stats for multiple keywords across marketplaces."""
    results = {}
    
    for keyword in keywords:
        results[keyword] = {}
        for mkt in marketplaces:
            cat_id = None
            if category_map and keyword in category_map:
                cat_info = category_map[keyword].get(mkt)
                if cat_info:
                    cat_id = cat_info.get("category_id")
            
            stats = get_sold_stats(keyword, mkt, cat_id, days)
            results[keyword][mkt] = stats
    
    return results

if __name__ == "__main__":
    print("=== Sold Data Test ===\n")
    
    test_keywords = ["Birkenstock Arizona", "Patagonia Nano Puff"]
    
    cat_map_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "category_map.json")
    category_map = None
    if os.path.exists(cat_map_path):
        with open(cat_map_path) as f:
            category_map = json.load(f)
    
    results = batch_sold_stats(test_keywords, category_map, marketplaces=("us",))
    
    print(f"\n=== Results ===")
    for kw, markets in results.items():
        for mkt, stats in markets.items():
            print(f"  {kw} ({mkt}): {stats}")