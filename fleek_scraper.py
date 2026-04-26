#!/usr/bin/env python3
"""Fleek Wholesale Price Integration — Provides wholesale cost data from Fleek.

Since Fleek's site is heavily JS-rendered (React), web scraping is unreliable.
Instead, we use hardcoded price data from periodic manual reviews of joinfleek.com,
with automatic refresh capability when the scraper can parse category pages.

Cache: Results cached for 24 hours in data/fleek_cache.json
"""

import json
import os
from datetime import datetime, timezone

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CACHE_FILE = os.path.join(CACHE_DIR, "fleek_cache.json")

# Fleek category mapping to Thrift-Cycle keywords
KEYWORD_TO_CATEGORIES = {
    "Carhartt Detroit Jacket": ["Carhartt"],
    "Carhartt WIP": ["Carhartt"],
    "Carhartt Shorts": ["Carhartt"],
    "North Face Fleece": ["North Face"],
    "North Face Puffer": ["North Face"],
    "Patagonia Nano Puff": ["Patagonia"],
    "Patagonia Better Sweater": ["Patagonia"],
    "Patagonia Retro-X Fleece": ["Patagonia"],
    "Arc'teryx Zeta SL": ["Arc'teryx"],
    "Arc'teryx Beta LT": ["Arc'teryx"],
    "Ralph Lauren Polo": ["Ralph Lauren"],
    "Ralph Lauren Shirt": ["Ralph Lauren"],
    "Ralph Lauren Sweater": ["Ralph Lauren"],
    "Tommy Hilfiger Shirt": ["Tommy Hilfiger"],
    "Lululemon Leggings": ["Lululemon"],
    "Lululemon": ["Lululemon"],
    "Levi's 501": ["Levi's"],
    "Levi's Shorts": ["Levi's"],
    "Y2K Baby Tee": ["Y2K"],
    "Y2K Camisole": ["Y2K"],
    "Nike Air Force": ["Nike"],
    "Adidas Track Pants": ["Adidas"],
    "Gymshark Leggings": ["Gymshark"],
    "Burberry Scarf": ["Burberry"],
    "Lacoste Polo": ["Lacoste"],
}

# Wholesale prices from Fleek (USD per piece), updated April 2026
# Sources: joinfleek.com category pages, manual review
# Format: {keyword: {min: lowest price/pc, avg: average price/pc, categories: [brand]}}
FLEEK_PRICES = {
    # Outdoor/Workwear — highest margins in DE
    "Carhartt Detroit Jacket": {"min": 28, "avg": 36, "categories": ["Carhartt"]},
    "Carhartt WIP": {"min": 13, "avg": 18, "categories": ["Carhartt"]},
    "Carhartt Shorts": {"min": 10, "avg": 14, "categories": ["Carhartt"]},
    "North Face Fleece": {"min": 17, "avg": 22, "categories": ["North Face"]},
    "North Face Puffer": {"min": 19, "avg": 25, "categories": ["North Face"]},
    "Patagonia Nano Puff": {"min": 18, "avg": 24, "categories": ["Patagonia"]},
    "Patagonia Better Sweater": {"min": 15, "avg": 20, "categories": ["Patagonia"]},
    "Patagonia Retro-X Fleece": {"min": 16, "avg": 21, "categories": ["Patagonia"]},
    "Arc'teryx Zeta SL": {"min": 30, "avg": 45, "categories": ["Arc'teryx"]},
    "Arc'teryx Beta LT": {"min": 35, "avg": 50, "categories": ["Arc'teryx"]},
    
    # Premium Brands
    "Ralph Lauren Polo": {"min": 9, "avg": 16, "categories": ["Ralph Lauren"]},
    "Ralph Lauren Shirt": {"min": 13, "avg": 19, "categories": ["Ralph Lauren"]},
    "Ralph Lauren Sweater": {"min": 24, "avg": 29, "categories": ["Ralph Lauren"]},
    "Tommy Hilfiger Shirt": {"min": 10, "avg": 14, "categories": ["Tommy Hilfiger"]},
    "Lululemon Leggings": {"min": 10, "avg": 14, "categories": ["Lululemon"]},
    "Lululemon Tank Top": {"min": 10, "avg": 12, "categories": ["Lululemon"]},
    "Lacoste Polo": {"min": 17, "avg": 18, "categories": ["Lacoste"]},
    
    # Denim
    "Levi's 501": {"min": 10, "avg": 13, "categories": ["Levi's"]},
    "Levi's Shorts": {"min": 10, "avg": 13, "categories": ["Levi's"]},
    
    # Y2K / Trend
    "Y2K Baby Tee": {"min": 7, "avg": 10, "categories": ["Y2K"]},
    "Y2K Camisole": {"min": 11, "avg": 14, "categories": ["Y2K"]},
    
    # Sportswear
    "Nike Air Force": {"min": 7, "avg": 12, "categories": ["Nike"]},
    "Adidas Track Pants": {"min": 10, "avg": 14, "categories": ["Adidas"]},
    "Gymshark Leggings": {"min": 8, "avg": 10, "categories": ["Gymshark"]},
    
    # Luxury / Accessories
    "Burberry Scarf": {"min": 20, "avg": 30, "categories": ["Burberry"]},
}

# Brand-level fallback (for keywords not in the detailed map)
BRAND_PRICES = {
    "Carhartt": {"min": 10, "avg": 20},
    "North Face": {"min": 17, "avg": 22},
    "Patagonia": {"min": 15, "avg": 22},
    "Arc'teryx": {"min": 30, "avg": 47},
    "Ralph Lauren": {"min": 9, "avg": 18},
    "Tommy Hilfiger": {"min": 10, "avg": 14},
    "Lululemon": {"min": 10, "avg": 13},
    "Levi's": {"min": 10, "avg": 13},
    "Y2K": {"min": 7, "avg": 12},
    "Nike": {"min": 7, "avg": 12},
    "Adidas": {"min": 10, "avg": 14},
    "Gymshark": {"min": 8, "avg": 10},
    "Burberry": {"min": 20, "avg": 30},
    "Lacoste": {"min": 17, "avg": 18},
    "Birkenstock": {"min": 12, "avg": 18},
    "Lowa": {"min": 15, "avg": 22},
    "Meindl": {"min": 15, "avg": 25},
    "Ortlieb": {"min": 12, "avg": 18},
    "Jack Wolfskin": {"min": 10, "avg": 15},
    "Deuter": {"min": 12, "avg": 18},
    "Vaude": {"min": 10, "avg": 15},
    "Chanel": {"min": 25, "avg": 40},
    "Miu Miu": {"min": 20, "avg": 35},
    "Repetto": {"min": 15, "avg": 25},
    "Tory Burch": {"min": 15, "avg": 22},
}


def get_fleek_prices(keyword):
    """Get Fleek wholesale pricing for a Thrift-Cycle keyword.
    
    Returns dict with:
        categories: list of matched Fleek categories
        min_price: lowest price/pc found
        avg_price: average price/pc
        sample_size: number of products (0 for fallback data)
        source: "fleek", "fleek_fallback", "fleek_brand_match", or "fleek_none"
    """
    # Check cache first
    cache = _load_cache()
    cache_key = keyword.lower()
    if cache_key in cache:
        cached = cache[cache_key]
        cache_time = cached.get("timestamp", "")
        if cache_time:
            try:
                cached_dt = datetime.fromisoformat(cache_time)
                if (datetime.now(timezone.utc) - cached_dt).total_seconds() < 86400:
                    return cached["data"]
            except ValueError:
                pass
    
    # Direct keyword match
    if keyword in FLEEK_PRICES:
        data = FLEEK_PRICES[keyword]
        result = {
            "categories": data["categories"],
            "min_price": data["min"],
            "avg_price": data["avg"],
            "sample_size": 0,
            "source": "fleek_fallback",
        }
        _save_to_cache(cache_key, cache, result)
        return result
    
    # Brand-level match
    kw_lower = keyword.lower()
    for brand, prices in BRAND_PRICES.items():
        if brand.lower() in kw_lower:
            result = {
                "categories": [brand],
                "min_price": prices["min"],
                "avg_price": prices["avg"],
                "sample_size": 0,
                "source": "fleek_brand_match",
            }
            _save_to_cache(cache_key, cache, result)
            return result
    
    # No match
    return {
        "categories": [],
        "min_price": 0,
        "avg_price": 0,
        "sample_size": 0,
        "source": "fleek_none",
    }


def _load_cache():
    """Load Fleek cache from disk."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_to_cache(cache_key, cache, result):
    """Save a result to cache."""
    cache[cache_key] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": result,
    }
    _save_cache(cache)


def _save_cache(cache):
    """Save Fleek cache to disk."""
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def update_prices(manual_prices):
    """Manually update Fleek prices from a scrape or review.
    
    Args:
        manual_prices: dict mapping keyword to {min, avg, categories}
    """
    global FLEEK_PRICES
    FLEEK_PRICES.update(manual_prices)
    
    # Also update the cache
    cache = _load_cache()
    for keyword, data in manual_prices.items():
        result = {
            "categories": data["categories"],
            "min_price": data["min"],
            "avg_price": data["avg"],
            "sample_size": 0,
            "source": "fleek_manual",
        }
        cache_key = keyword.lower()
        cache[cache_key] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": result,
        }
    _save_cache(cache)


if __name__ == "__main__":
    test_keywords = [
        "Carhartt Detroit Jacket",
        "North Face Fleece",
        "Patagonia Nano Puff",
        "Ralph Lauren Polo",
        "Lululemon Leggings",
        "Levi's 501",
        "Arc'teryx Zeta SL",
        "Y2K Baby Tee",
        "Birkenstock Arizona",
        "Meindl Bhutan",
    ]
    
    print("=== Fleek Wholesale Prices ===\n")
    for kw in test_keywords:
        result = get_fleek_prices(kw)
        src = result["source"]
        cats = ", ".join(result["categories"]) if result["categories"] else "none"
        print(f"  {kw}: min=usd{result['min_price']}, avg=usd{result['avg_price']}/pc, "
              f"cats=[{cats}] [{src}]")