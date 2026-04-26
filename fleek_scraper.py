#!/usr/bin/env python3
"""Fleek Wholesale Scraper — Scrapes joinfleek.com for wholesale pricing data.

Scrapes Fleek's category pages to extract:
- Product name, category, price per piece
- Rating, discount, seller info
- Maps Fleek categories to Thrift-Cycle keywords

Cache: Results cached for 24 hours in data/fleek_cache.json
"""

import json
import os
import re
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from statistics import mean

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CACHE_FILE = os.path.join(CACHE_DIR, "fleek_cache.json")

FLEEK_BASE = "https://www.joinfleek.com"

# Fleek category URLs mapped to Thrift-Cycle keywords
CATEGORY_MAP = {
    # Outdoor/Workwear
    "Carhartt": "/collections/carhartt-vintage-wholesale",
    "North Face": "/collections/the-north-face",
    "Patagonia": "/collections/patagonia",
    "Arc'teryx": "/collections/arcteryx",
    
    # Premium Brands
    "Ralph Lauren": "/collections/ralph-lauren",
    "Tommy Hilfiger": "/collections/tommy-hilfiger",
    "Lacoste": "/collections/lacoste",
    "Lululemon": "/collections/lululemon",
    
    # Denim
    "Levi's": "/collections/levis",
    "Jeans": "/collections/jeans",
    
    # Y2K / Trend
    "Y2K": "/collections/y2k",
    
    # Sportswear
    "Nike": "/collections/nike",
    "Adidas": "/collections/adidas",
    "Gymshark": "/collections/gymshark",
    
    # Accessories
    "Burberry": "/collections/burberry",
    "Fila": "/collections/fila",
}

# Keywords that map to multiple Fleek categories
KEYWORD_TO_CATEGORIES = {
    "Carhartt Detroit Jacket": ["Carhartt"],
    "Carhartt WIP": ["Carhartt"],
    "North Face Fleece": ["North Face"],
    "North Face Puffer": ["North Face"],
    "Patagonia Nano Puff": ["Patagonia"],
    "Patagonia Better Sweater": ["Patagonia"],
    "Arc'teryx Zeta SL": ["Arc'teryx"],
    "Arc'teryx Beta LT": ["Arc'teryx"],
    "Ralph Lauren Polo": ["Ralph Lauren"],
    "Tommy Hilfiger Shirt": ["Tommy Hilfiger"],
    "Lululemon Leggings": ["Lululemon"],
    "Lululemon": ["Lululemon"],
    "Levi's 501": ["Levi's", "Jeans"],
    "Levi's Vintage": ["Levi's", "Jeans"],
    "Y2K Baby Tee": ["Y2K"],
    "Nike Air Force": ["Nike"],
    "Adidas Track Pants": ["Adidas"],
    "Gymshark": ["Gymshark"],
    "Burberry Scarf": ["Burberry"],
    "Lacoste Polo": ["Lacoste"],
    "Fila Disruptor": ["Fila"],
}

# Generic fallback: try to match keyword to category
def find_categories(keyword):
    """Find Fleek categories for a Thrift-Cycle keyword."""
    if keyword in KEYWORD_TO_CATEGORIES:
        return KEYWORD_TO_CATEGORIES[keyword]
    
    cats = []
    for brand in CATEGORY_MAP:
        if brand.lower() in keyword.lower():
            cats.append(brand)
    if cats:
        return cats
    return []


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _parse_price(text):
    """Extract USD price from text like '$13.59/pc' or '$220'."""
    match = re.search(r'\$(\d+\.?\d*)', text)
    if match:
        return float(match.group(1))
    return None


def _parse_rating(text):
    """Extract rating from text like '4.7' or '4.7/5'."""
    match = re.search(r'(\d+\.?\d*)', text)
    if match:
        val = float(match.group(1))
        return val if 0 <= val <= 5 else None
    return None


def _parse_discount(text):
    """Extract discount percentage from text like '30% Discount'."""
    match = re.search(r'(\d+)%', text)
    if match:
        return int(match.group(1))
    return 0


def scrape_category(category_name, max_retries=2):
    """Scrape a Fleek category page for wholesale pricing.
    
    Returns list of dicts with keys:
        name, category, price_per_pc, original_price, discount, rating, url
    """
    slug = CATEGORY_MAP.get(category_name)
    if not slug:
        return []
    
    url = f"{FLEEK_BASE}{slug}"
    products = []
    
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Category doesn't exist, try search
                return scrape_search(category_name)
            elif attempt < max_retries - 1:
                time.sleep(2)
                continue
            else:
                return []
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return []
    
    # Parse product listings from HTML
    # Fleek renders server-side with product cards containing price info
    # Pattern: "$<price>" and "/pc" for per-piece pricing
    
    # Find all price patterns - Fleek shows "$XX.XX/pc" for wholesale
    price_matches = re.finditer(
        r'\$(\d+(?:\.\d{1,2})?)\s*[/]\s*pc|'
        r'\$(\d+(?:,\d{3})*(?:\.\d{1,2})?)\s*(?:\n|$|<)',
        html
    )
    
    # More robust: find product blocks with name + price
    # Fleek uses structured product data in script tags or JSON-LD
    json_ld = re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    
    for block in json_ld:
        try:
            data = json.loads(block)
            if isinstance(data, list):
                for item in data:
                    if item.get("@type") == "Product":
                        name = item.get("name", "")
                        offers = item.get("offers", {})
                        price = offers.get("price", 0)
                        if name and price:
                            products.append({
                                "name": name,
                                "category": category_name,
                                "price_per_pc": float(price),
                                "original_price": float(price),
                                "discount": 0,
                                "rating": None,
                                "url": item.get("url", ""),
                            })
        except (json.JSONDecodeError, TypeError):
            continue
    
    # If no JSON-LD, try scraping from HTML text content
    if not products:
        # Look for product patterns in the rendered text
        # Fleek shows: "Product Name ★4.7 $104 $10.43/pc Shipping Inc."
        product_blocks = re.finditer(
            r'([A-Z][^$]*?)'  # product name (greedy)
            r'★?([\d.]+)?\s*'  # optional rating
            r'\$(\d+(?:,\d{3})*(?:\.\d{1,2})?)\s*'  # sale price
            r'(?:\$(\d+(?:,\d{3})*(?:\.\d{1,2})?))?\s*'  # original price (optional)
            r'(?:\$([\d.]+)/pc)?',  # per-piece price (optional)
            html
        )
        for match in product_blocks:
            name = match.group(1).strip()[:100]
            rating = _parse_rating(match.group(2)) if match.group(2) else None
            price = _parse_price(match.group(3) or match.group(5) or "0")
            orig_price = _parse_price(match.group(4)) if match.group(4) else price
            
            if price and price > 0 and len(name) > 5:
                discount = round((1 - price / orig_price) * 100) if orig_price and orig_price > price else 0
                products.append({
                    "name": name,
                    "category": category_name,
                    "price_per_pc": price,
                    "original_price": orig_price or price,
                    "discount": discount,
                    "rating": rating,
                    "url": "",
                })
    
    # Deduplicate by name
    seen = set()
    unique = []
    for p in products:
        key = p["name"][:50]
        if key not in seen:
            seen.add(key)
            unique.append(p)
    
    return unique


def scrape_search(query, max_retries=2):
    """Search Fleek for products matching a query.
    
    Falls back to this when a category page doesn't exist.
    """
    params = urllib.parse.urlencode({"q": query, "type": "product"})
    url = f"{FLEEK_BASE}/search?{params}"
    
    # Note: Fleek search may be JS-rendered. Return empty if we can't parse.
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return []
    
    # Try JSON-LD first
    json_ld = re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    
    products = []
    for block in json_ld:
        try:
            data = json.loads(block)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict) and item.get("@type") == "Product":
                    name = item.get("name", "")
                    offers = item.get("offers", {})
                    price = offers.get("price", 0)
                    if name and price:
                        products.append({
                            "name": name,
                            "category": query,
                            "price_per_pc": float(price),
                            "original_price": float(price),
                            "discount": 0,
                            "rating": None,
                            "url": item.get("url", ""),
                        })
        except (json.JSONDecodeError, TypeError):
            continue
    
    return products


def get_fleek_prices(keyword):
    """Get Fleek wholesale pricing for a Thrift-Cycle keyword.
    
    Returns dict with:
        categories: list of matched Fleek categories
        products: list of product dicts
        min_price: lowest price/pc found
        avg_price: average price/pc
        sample_size: number of products found
        source: "fleek" or "fleek_cached"
    """
    # Check cache
    cache = _load_cache()
    cache_key = keyword.lower()
    if cache_key in cache:
        cached = cache[cache_key]
        cache_time = cached.get("timestamp", "")
        if cache_time:
            try:
                cached_dt = datetime.fromisoformat(cache_time)
                if (datetime.now(timezone.utc) - cached_dt).total_seconds() < 86400:  # 24h
                    return cached["data"]
            except ValueError:
                pass
    
    categories = find_categories(keyword)
    if not categories:
        # Try search fallback
        products = scrape_search(keyword)
        if not products:
            return {
                "categories": [],
                "products": [],
                "min_price": 0,
                "avg_price": 0,
                "sample_size": 0,
                "source": "fleek_none",
            }
    else:
        products = []
        for cat in categories:
            products.extend(scrape_category(cat))
            time.sleep(1)  # Rate limit
    
    if not products:
        # Hardcoded fallback prices from our April 2026 scrape
        fallback = _get_fallback_prices(keyword)
        return fallback
    
    prices = [p["price_per_pc"] for p in products if p["price_per_pc"] > 0]
    
    result = {
        "categories": categories,
        "products": products[:10],  # Top 10 relevant
        "min_price": round(min(prices), 2) if prices else 0,
        "avg_price": round(mean(prices), 2) if prices else 0,
        "sample_size": len(prices),
        "source": "fleek",
    }
    
    # Save to cache
    cache[cache_key] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": result,
    }
    _save_cache(cache)
    
    return result


def _get_fallback_prices(keyword):
    """Return hardcoded Fleek prices from April 2026 scrape for common keywords."""
    # Prices in USD per piece, from Fleek's top listings
    fallbacks = {
        "Carhartt Detroit Jacket": {"min": 28, "avg": 36, "categories": ["Carhartt"]},
        "Carhartt WIP": {"min": 13, "avg": 18, "categories": ["Carhartt"]},
        "Carhartt Shorts": {"min": 10, "avg": 14, "categories": ["Carhartt"]},
        "North Face Fleece": {"min": 17, "avg": 22, "categories": ["North Face"]},
        "North Face Puffer": {"min": 19, "avg": 25, "categories": ["North Face"]},
        "Patagonia Nano Puff": {"min": 18, "avg": 24, "categories": ["Patagonia"]},
        "Patagonia Better Sweater": {"min": 15, "avg": 20, "categories": ["Patagonia"]},
        "Arc'teryx Zeta SL": {"min": 30, "avg": 45, "categories": ["Arc'teryx"]},
        "Arc'teryx Beta LT": {"min": 35, "avg": 50, "categories": ["Arc'teryx"]},
        "Ralph Lauren Polo": {"min": 9, "avg": 16, "categories": ["Ralph Lauren"]},
        "Ralph Lauren Shirt": {"min": 13, "avg": 19, "categories": ["Ralph Lauren"]},
        "Ralph Lauren Sweater": {"min": 24, "avg": 29, "categories": ["Ralph Lauren"]},
        "Tommy Hilfiger Shirt": {"min": 10, "avg": 14, "categories": ["Tommy Hilfiger"]},
        "Lululemon Leggings": {"min": 10, "avg": 14, "categories": ["Lululemon"]},
        "Lululemon Tank Top": {"min": 10, "avg": 12, "categories": ["Lululemon"]},
        "Levi's 501": {"min": 10, "avg": 13, "categories": ["Levi's"]},
        "Levi's Shorts": {"min": 10, "avg": 13, "categories": ["Levi's"]},
        "Y2K Baby Tee": {"min": 7, "avg": 10, "categories": ["Y2K"]},
        "Y2K Camisole": {"min": 11, "avg": 14, "categories": ["Y2K"]},
        "Nike Air Force": {"min": 7, "avg": 12, "categories": ["Nike"]},
        "Adidas Track Pants": {"min": 10, "avg": 14, "categories": ["Adidas"]},
        "Gymshark Leggings": {"min": 8, "avg": 10, "categories": ["Gymshark"]},
        "Burberry Scarf": {"min": 20, "avg": 30, "categories": ["Burberry"]},
        "Lacoste Polo": {"min": 17, "avg": 18, "categories": ["Lacoste"]},
    }
    
    kw_lower = keyword.lower()
    for key, data in fallbacks.items():
        if key.lower() in kw_lower or kw_lower in key.lower():
            return {
                "categories": data["categories"],
                "products": [],
                "min_price": data["min"],
                "avg_price": data["avg"],
                "sample_size": 0,
                "source": "fleek_fallback",
            }
    
    # Generic brand matching
    for brand in CATEGORY_MAP:
        if brand.lower() in kw_lower:
            return {
                "categories": [brand],
                "products": [],
                "min_price": 0,
                "avg_price": 0,
                "sample_size": 0,
                "source": "fleek_brand_match",
            }
    
    return {
        "categories": [],
        "products": [],
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


def _save_cache(cache):
    """Save Fleek cache to disk."""
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


if __name__ == "__main__":
    # Test with key brands
    test_keywords = [
        "Carhartt Detroit Jacket",
        "North Face Fleece", 
        "Patagonia Nano Puff",
        "Ralph Lauren Polo",
        "Lululemon Leggings",
        "Levi's 501",
        "Arc'teryx Zeta SL",
        "Y2K Baby Tee",
    ]
    
    print("=== Fleek Wholesale Price Test ===\n")
    for kw in test_keywords:
        result = get_fleek_prices(kw)
        src = result["source"]
        print(f"  {kw}: ${result['avg_price']:.2f}/pc avg, ${result['min_price']:.2f} min, "
              f"{result['sample_size']} products [{src}]")
        if result["products"]:
            for p in result["products"][:3]:
                print(f"    - {p['name'][:50]}: ${p['price_per_pc']:.2f}/pc")
        print()