#!/usr/bin/env python3
"""eBay Browse API — Active listing counts for Thrift-Cycle.

For each keyword + category, returns total active count split by buying option.
Uses stdlib only (urllib, json).
"""

import json
import time
import urllib.request
import urllib.error
import urllib.parse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dns_patch
from ebay_auth import get_token

BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

MARKETPLACES = {
    "de": "EBAY-DE",
    "us": "EBAY-US",
}

_last_call_time = 0.0
_MIN_INTERVAL = 0.21  # ~5 calls/sec max


def _rate_limit():
    """Enforce 5 calls/sec max across this module."""
    global _last_call_time
    elapsed = time.time() - _last_call_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_call_time = time.time()


def search_active(keyword, marketplace="us", category_id=None, buying_option=None, limit=1):
    """Search active listings. Returns dict with total and sample items.

    Args:
        keyword: search query string
        marketplace: 'de' or 'us'
        category_id: optional eBay category ID
        buying_option: 'FIXED_PRICE' or 'AUCTION' or None for both
        limit: how many items to fetch (default 1, just for total)

    Returns:
        {
            "total": int,
            "items": [{item_id, title, price, item_creation_date, buying_options}],
            "error": str | None,
        }
    """
    _rate_limit()
    mp = MARKETPLACES.get(marketplace, "EBAY-US")

    params = {
        "q": keyword,
        "limit": str(min(limit, 200)),
        "offset": "0",
    }

    filters = []
    if category_id:
        filters.append(f"categoryId:{{{category_id}}}")
    if buying_option:
        filters.append(f"buyingOptions:{{{buying_option}}}")
    filters.append("conditions:{USED}")

    if filters:
        params["filter"] = " ".join(filters)

    url = f"{BROWSE_URL}?{urllib.parse.urlencode(params)}"

    token = get_token()
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-EBAY-C-MARKETPLACE-ID": mp,
    })

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {"total": 0, "items": [], "error": f"HTTP {e.code}: {body[:500]}"}
    except Exception as e:
        return {"total": 0, "items": [], "error": str(e)}

    total = data.get("total", 0)
    if isinstance(total, str):
        total = int(total) if total.isdigit() else 0

    items = []
    for item in data.get("itemSummaries", []):
        price = item.get("price", {})
        items.append({
            "item_id": item.get("itemId", ""),
            "title": item.get("title", ""),
            "price": float(price.get("value", 0)) if price else 0,
            "currency": price.get("currency", "USD") if price else "USD",
            "item_creation_date": item.get("itemCreationDate", ""),
            "buying_options": item.get("buyingOptions", []),
        })

    return {"total": total, "items": items, "error": None}


def get_active_counts(keyword, marketplace="us", category_id=None):
    """Get active listing counts split by buying option.

    Returns:
        {
            "total": int,          # total active USED listings
            "fixed_price": int,    # FIXED_PRICE count
            "auction": int,        # AUCTION count
            "items": [...],        # sample items for listing age
            "error": str | None,
        }
    """
    # Query: all used
    all_result = search_active(keyword, marketplace, category_id, None, limit=50)
    if all_result.get("error"):
        return {
            "total": 0, "fixed_price": 0, "auction": 0,
            "items": [], "error": all_result["error"],
        }

    total = all_result.get("total", 0)

    # Query: fixed price only
    fp_result = search_active(keyword, marketplace, category_id, "FIXED_PRICE", limit=1)
    fp_total = fp_result.get("total", 0) if not fp_result.get("error") else 0

    # Query: auction only
    auc_result = search_active(keyword, marketplace, category_id, "AUCTION", limit=1)
    auc_total = auc_result.get("total", 0) if not auc_result.get("error") else 0

    # Fallback: if FP+AUC > total, use total as upper bound
    if fp_total + auc_total > total and total > 0:
        # Scale proportionally
        ratio = total / (fp_total + auc_total)
        fp_total = int(fp_total * ratio)
        auc_total = total - fp_total
    elif total == 0 and (fp_total > 0 or auc_total > 0):
        total = fp_total + auc_total

    return {
        "total": total,
        "fixed_price": fp_total,
        "auction": auc_total,
        "items": all_result.get("items", []),
        "error": None,
    }


def batch_active_counts(keywords, category_map=None, marketplaces=("de", "us")):
    """Get active counts for multiple keywords across marketplaces.

    Returns:
        {keyword: {marketplace: {total, fixed_price, auction}}}
    """
    results = {}
    for keyword in keywords:
        results[keyword] = {}
        for mkt in marketplaces:
            cat_id = None
            if category_map and keyword in category_map:
                cat_info = category_map[keyword].get(mkt)
                if cat_info:
                    cat_id = cat_info.get("category_id")

            counts = get_active_counts(keyword, mkt, cat_id)
            results[keyword][mkt] = {
                "total": counts["total"],
                "fixed_price": counts["fixed_price"],
                "auction": counts["auction"],
            }
            print(f"  {keyword} ({mkt}): total={counts['total']}, "
                  f"bin={counts['fixed_price']}, auc={counts['auction']}")
    return results


if __name__ == "__main__":
    print("=== Browse API Test ===\n")
    test_keywords = ["Birkenstock Arizona", "Patagonia Nano Puff"]

    cat_map_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "category_map.json"
    )
    category_map = None
    if os.path.exists(cat_map_path):
        with open(cat_map_path) as f:
            category_map = json.load(f)
        print(f"Loaded category map ({len(category_map)} keywords)")

    results = batch_active_counts(test_keywords, category_map, marketplaces=("us",))

    print(f"\n=== Results ===")
    for kw, markets in results.items():
        for mkt, counts in markets.items():
            print(f"  {kw} ({mkt}): {counts}")
