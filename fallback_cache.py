#!/usr/bin/env python3
"""Fallback cache for eBay Finding API when rate-limited.

Loads the most recent cached sold stats from data/sold_*.json files.
"""

import json
import glob
from pathlib import Path
from statistics import mean, median

DATA_DIR = Path(__file__).parent / "data"


def get_cached_sold_stats(keyword, marketplace="de"):
    """Load most recent cached sold stats for a keyword/marketplace.
    
    Returns dict matching get_sold_stats() output, or None if no cache found.
    """
    safe_kw = keyword.replace(" ", "_").replace("'", "\\'")
    pattern = str(DATA_DIR / f"sold_{marketplace}_{safe_kw}_*.json")
    
    # Also try without backslash escaping for apostrophe
    files = glob.glob(pattern)
    if not files:
        # Try with raw apostrophe
        safe_kw2 = keyword.replace(" ", "_")
        pattern2 = str(DATA_DIR / f"sold_{marketplace}_{safe_kw2}_*.json")
        files = glob.glob(pattern2)
    
    if not files:
        return None
    
    # Get most recent file by date in filename
    def _date_from_filename(f):
        stem = Path(f).stem  # e.g., "sold_de_Birkenstock_Arizona_2026-04-26"
        parts = stem.split("_")
        # Last 3 parts are the date: 2026-04-26
        if len(parts) >= 3 and parts[-3].isdigit():
            return "_".join(parts[-3:])
        return ""
    
    files.sort(key=_date_from_filename, reverse=True)
    most_recent = files[0]
    
    try:
        with open(most_recent) as f:
            cached = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None
    
    sold_count = cached.get("sold_count", 0)
    avg_price = cached.get("avg_price", 0)
    prices = cached.get("prices", [])
    
    return {
        "sold_count": sold_count,
        "fetched_count": cached.get("fetched_count", 0),
        "avg_price": avg_price,
        "median_price": round(median(prices), 2) if prices else 0,
        "min_price": round(min(prices), 2) if prices else 0,
        "max_price": round(max(prices), 2) if prices else 0,
        "prices": prices,
        "items": cached.get("items", []),
        "by_option": {
            "FIXED_PRICE": {
                "sold_count": sold_count,
                "avg_price": avg_price,
                "median_price": round(median(prices), 2) if prices else 0,
                "min_price": round(min(prices), 2) if prices else 0,
                "max_price": round(max(prices), 2) if prices else 0,
                "prices": prices,
            },
            "AUCTION": {
                "sold_count": 0,
                "avg_price": 0,
                "median_price": 0,
                "min_price": 0,
                "max_price": 0,
                "prices": [],
            },
        },
        "error": None,
        "_cached": True,
        "_cache_date": _date_from_filename(most_recent),
        "_cache_file": most_recent,
    }


def test():
    print("=== Fallback Cache Test ===")
    for kw, mkt in [("Birkenstock Arizona", "de"), ("Patagonia Nano Puff", "us")]:
        result = get_cached_sold_stats(kw, mkt)
        if result:
            print(f"{kw} ({mkt}): cached={result['_cached']}, "
                  f"date={result['_cache_date']}, "
                  f"sold={result['sold_count']}, avg=${result['avg_price']}")
        else:
            print(f"{kw} ({mkt}): NO CACHE")


if __name__ == "__main__":
    test()
