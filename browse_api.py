#!/usr/bin/env python3
"""eBay Browse API client — Active listing counts for Thrift-Cycle.
REVISED: Uses fieldgroups for buying option breakdowns and condition distributions.
"""

import json
import time
import urllib.request
import urllib.parse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ebay_auth import get_token

BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

MARKETPLACES = {
    "de": "EBAY-DE",
    "us": "EBAY-US",
}

RATE_LIMIT_DELAY = 0.25

def search_active(keyword, marketplace="EBAY-US", category_id=None, condition=None, limit=1, fieldgroups=None):
    """Search active listings on eBay Browse API.
    
    Returns dict with: total, item_summaries, refinements
    """
    token = get_token()
    
    params = {
        "q": keyword,
        "marketplace_ids": marketplace,
        "limit": str(limit),
    }
    if category_id:
        params["category_ids"] = str(category_id)
    if condition:
        params["filter"] = f"conditions:{condition}"
    if fieldgroups:
        params["fieldgroups"] = fieldgroups
    
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
        body = e.read().decode()
        print(f"Browse API error ({e.code}): {body[:300]}", file=sys.stderr)
        return {"total": 0, "error": e.code, "raw_error": body[:500]}
    
    total = data.get("total", 0)
    if isinstance(total, str):
        total = int(total) if total.isdigit() else 0
    
    result = {"total": total, "items": [], "refinements": {}}
    
    # Extract refinements
    refinement = data.get("refinement", {})
    if refinement:
        # Buying option distributions
        for bo in refinement.get("buyingOptionDistributions", []):
            result["refinements"].setdefault("buying_options", {})[bo["buyingOption"]] = bo["matchCount"]
        # Condition distributions
        for cd in refinement.get("conditionDistributions", []):
            cond = cd.get("condition", "").upper()
            result["refinements"].setdefault("conditions", {})[cond] = cd["matchCount"]
    
    # Extract price data from items
    prices = []
    for item in data.get("itemSummaries", []):
        price = item.get("price", {})
        if price and "value" in price:
            prices.append(float(price["value"]))
    
    result["prices"] = prices
    result["sample_size"] = len(prices)
    
    return result

def get_active_counts(keyword, marketplace="us", category_id=None):
    """Get comprehensive active listing data for a keyword.
    
    Returns: {total, buying_options: {FIXED_PRICE: N, AUCTION: N}, conditions: {Used: N, New: N}, avg_price}
    """
    mp = MARKETPLACES.get(marketplace, marketplace)
    
    # Query 1: Total count + buying option + condition breakdowns (FULL gives everything)
    result_total = search_active(keyword, mp, category_id, fieldgroups="FULL")
    time.sleep(RATE_LIMIT_DELAY)
    
    # Query 2: Sample items for price data (used condition)
    result_used = search_active(keyword, mp, category_id, condition="USED", limit=50)
    time.sleep(RATE_LIMIT_DELAY)
    
    # Build result
    total = result_total.get("total", 0)
    buying_options = result_total.get("refinements", {}).get("buying_options", {})
    conditions = result_total.get("refinements", {}).get("conditions", {})
    
    used_prices = result_used.get("prices", [])
    avg_price = sum(used_prices) / len(used_prices) if used_prices else 0
    median_price = sorted(used_prices)[len(used_prices)//2] if used_prices else 0
    
    return {
        "total": total,
        "fixed_price": buying_options.get("FIXED_PRICE", 0),
        "auction": buying_options.get("AUCTION", 0),
        "used_count": conditions.get("USED", conditions.get("Used", conditions.get("Pre-owned", 0))),
        "new_count": conditions.get("NEW", conditions.get("New", 0)),
        "avg_used_price": round(avg_price, 2),
        "median_used_price": round(median_price, 2),
        "sample_size": len(used_prices),
    }

def batch_active_counts(keywords, category_map=None, marketplaces=("de", "us")):
    """Get active counts for multiple keywords across marketplaces."""
    results = {}
    
    for keyword in keywords:
        results[keyword] = {}
        for mkt in marketplaces:
            cat_id = None
            if category_map and keyword in category_map:
                cat_info = category_map[keyword].get(mkt)
                if cat_info:
                    cat_id = cat_info.get("category_id")
            
            print(f"  Fetching {keyword} ({mkt})...", end=" ", flush=True)
            counts = get_active_counts(keyword, mkt, cat_id)
            results[keyword][mkt] = counts
            print(f"total={counts['total']}, bin={counts['fixed_price']}, auc={counts['auction']}, used=${counts['avg_used_price']}")
    
    return results

if __name__ == "__main__":
    print("=== Browse API Test ===\n")
    
    test_keywords = ["Birkenstock Arizona", "Patagonia Nano Puff"]
    
    cat_map_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "category_map.json")
    category_map = None
    if os.path.exists(cat_map_path):
        with open(cat_map_path) as f:
            category_map = json.load(f)
        print(f"Loaded category map ({len(category_map)} keywords)")
    
    results = batch_active_counts(test_keywords, category_map)
    
    print(f"\n=== Results ===")
    for kw, markets in results.items():
        for mkt, counts in markets.items():
            print(f"  {kw} ({mkt}): {counts}")