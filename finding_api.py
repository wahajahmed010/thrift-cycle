#!/usr/bin/env python3
"""eBay Finding API — Sold listings data via XML/SOAP REST payload.
Uses findCompletedItems with SoldItemsOnly filter.

Updated 2026-04-29:
- Increased rate limit interval (1.0s) to avoid eBay daily rate limits
- Added exponential backoff retry for rate limit errors (max 3 retries)
- Fixed silent failure: rate limit errors now propagate properly
"""

import json
import time
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from statistics import mean, median
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ebay_auth import load_credentials
from quota_tracker import (
    increment_calls, get_remaining_calls, is_quota_exceeded,
    FINDING_DAILY_LIMIT, reset_if_new_day
)

FINDING_URL = "https://svcs.ebay.com/services/search/FindingService/v1"
APP_ID = load_credentials()[0]

GLOBAL_IDS = {"de": "EBAY-DE", "us": "EBAY-US"}

_last_call_time = 0.0
# eBay Finding API: ~5 calls/sec max per IP, but ALSO daily limits per App ID
# We use 1.0s to be safe and avoid the daily quota exhaustion
_MIN_INTERVAL = 1.0
_MAX_RETRIES = 3
_RETRY_DELAY = 2.0  # Initial retry delay in seconds

# Minimum calls to reserve for critical operations
_MIN_RESERVE = 10


def _rate_limit():
    global _last_call_time
    elapsed = time.time() - _last_call_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_call_time = time.time()


def _local_name(tag):
    return tag.split("}")[1] if "}" in tag else tag


def _find_first(parent, tag_name):
    for child in parent:
        if _local_name(child.tag) == tag_name:
            return child
    return None


def _findall_children(parent, tag_name):
    return [c for c in parent if _local_name(c.tag) == tag_name]


def _parse_finding_response(xml_bytes):
    """Parse Finding API XML response."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        return [], 0, 0, "Failure", f"XML parse error: {e}"

    ack_elem = _find_first(root, "ack")
    ack = ack_elem.text if ack_elem is not None else "Unknown"

    # Check for rate limit error specifically
    if ack != "Success":
        error_msg = "Unknown error"
        error_id = None
        error_domain = None
        
        error_msg_elem = _find_first(root, "errorMessage")
        if error_msg_elem is not None:
            error_elem = _find_first(error_msg_elem, "error")
            if error_elem is not None:
                msg_elem = _find_first(error_elem, "message")
                if msg_elem is not None:
                    error_msg = msg_elem.text
                error_id_elem = _find_first(error_elem, "errorId")
                if error_id_elem is not None:
                    error_id = error_id_elem.text
                domain_elem = _find_first(error_elem, "domain")
                if domain_elem is not None:
                    error_domain = domain_elem.text
        
        # Rate limit detection
        is_rate_limit = (
            error_id == "10001" or 
            (error_domain and "RateLimiter" in error_domain) or
            "exceeded the number of times" in (error_msg or "")
        )
        
        if is_rate_limit:
            return [], 0, 0, "RateLimit", error_msg
        
        return [], 0, 0, ack, error_msg

    search_result = _find_first(root, "searchResult")
    items = []
    if search_result is not None:
        for item in _findall_children(search_result, "item"):
            item_id, title, price, currency = "", "", 0.0, "USD"
            listing_type, end_time, condition_id, selling_state = "", "", "", ""

            item_id_elem = _find_first(item, "itemId")
            if item_id_elem is not None:
                item_id = item_id_elem.text or ""
            title_elem = _find_first(item, "title")
            if title_elem is not None:
                title = title_elem.text or ""
            selling_status = _find_first(item, "sellingStatus")
            if selling_status is not None:
                price_elem = _find_first(selling_status, "currentPrice")
                if price_elem is not None:
                    try:
                        price = float(price_elem.text or 0)
                    except ValueError:
                        price = 0.0
                    currency = price_elem.get("currencyId") or "USD"
                state_elem = _find_first(selling_status, "sellingState")
                if state_elem is not None:
                    selling_state = state_elem.text or ""
            listing_info = _find_first(item, "listingInfo")
            if listing_info is not None:
                type_elem = _find_first(listing_info, "listingType")
                if type_elem is not None:
                    listing_type = type_elem.text or ""
                end_elem = _find_first(listing_info, "endTime")
                if end_elem is not None:
                    end_time = end_elem.text or ""
            condition = _find_first(item, "condition")
            if condition is not None:
                cond_id_elem = _find_first(condition, "conditionId")
                if cond_id_elem is not None:
                    condition_id = cond_id_elem.text or ""

            items.append({
                "item_id": item_id, "title": title, "price": price,
                "currency": currency, "listing_type": listing_type,
                "end_time": end_time, "condition_id": condition_id,
                "selling_state": selling_state,
            })

    pagination = _find_first(root, "paginationOutput")
    total_entries, total_pages = 0, 0
    if pagination is not None:
        total_entries_elem = _find_first(pagination, "totalEntries")
        if total_entries_elem is not None:
            try:
                total_entries = int(total_entries_elem.text or 0)
            except ValueError:
                total_entries = 0
        total_pages_elem = _find_first(pagination, "totalPages")
        if total_pages_elem is not None:
            try:
                total_pages = int(total_pages_elem.text or 0)
            except ValueError:
                total_pages = 0

    return items, total_entries, total_pages, ack, None


def _call_finding_api(keyword, global_id, days=30, page=1, retry_count=0):
    """Make a single Finding API call via GET with query params.
    
    Retries on rate limit errors with exponential backoff.
    """
    # Check quota before making call
    reset_if_new_day()
    remaining = get_remaining_calls("finding")
    if remaining <= _MIN_RESERVE:
        return [], 0, 0, "QuotaExceeded", (
            f"Daily quota exceeded ({FINDING_DAILY_LIMIT} calls). "
            f"Used: {get_remaining_calls('finding') + _MIN_RESERVE}"
        )
    
    _rate_limit()
    increment_calls("finding", 1)
    end_to = datetime.now(timezone.utc)
    end_from = end_to - timedelta(days=days)

    params = {
        "OPERATION-NAME": "findCompletedItems",
        "SERVICE-VERSION": "1.13.0",
        "SECURITY-APPNAME": APP_ID,
        "RESPONSE-DATA-FORMAT": "XML",
        "REST-PAYLOAD": "",
        "keywords": keyword,
        "paginationInput.entriesPerPage": "100",
        "paginationInput.pageNumber": str(page),
        "itemFilter(0).name": "SoldItemsOnly",
        "itemFilter(0).value": "true",
        "itemFilter(1).name": "Condition",
        "itemFilter(1).value": "3000",
        "itemFilter(2).name": "EndTimeFrom",
        "itemFilter(2).value": end_from.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "itemFilter(3).name": "EndTimeTo",
        "itemFilter(3).value": end_to.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }

    url = f"{FINDING_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Content-Type": "application/json",
        "X-EBAY-SOA-OPERATION-NAME": "findCompletedItems",
        "X-EBAY-SOA-SECURITY-APPNAME": APP_ID,
    })

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            xml_bytes = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        
        # Check if it's a rate limit error
        is_rate_limit = (
            e.code == 500 and 
            ("RateLimiter" in body or "exceeded the number of times" in body)
        )
        
        if is_rate_limit and retry_count < _MAX_RETRIES:
            # Decrement counter since call didn't succeed
            increment_calls("finding", -1)
            delay = _RETRY_DELAY * (2 ** retry_count)
            print(f"  [Finding API] Rate limited, retrying in {delay}s (attempt {retry_count + 1}/{_MAX_RETRIES})...")
            time.sleep(delay)
            return _call_finding_api(keyword, global_id, days, page, retry_count + 1)
        
        return [], 0, 0, "Failure", f"HTTP {e.code}: {body[:500]}"
    except Exception as e:
        return [], 0, 0, "Failure", str(e)

    items, entries, pages, ack, error = _parse_finding_response(xml_bytes)
    
    # Handle rate limit from parsed response
    if ack == "RateLimit" and retry_count < _MAX_RETRIES:
        # Decrement counter since call didn't succeed
        increment_calls("finding", -1)
        delay = _RETRY_DELAY * (2 ** retry_count)
        print(f"  [Finding API] Rate limited (ack), retrying in {delay}s (attempt {retry_count + 1}/{_MAX_RETRIES})...")
        time.sleep(delay)
        return _call_finding_api(keyword, global_id, days, page, retry_count + 1)
    
    return items, entries, pages, ack, error


def find_completed_items(keyword, marketplace="de", days=30):
    """Fetch sold listings for a keyword with pagination.
    Returns dict with items, sold_count, avg_price, min/max, error.
    """
    global_id = GLOBAL_IDS.get(marketplace, "EBAY-US")
    all_items, total_entries = [], 0
    page, max_pages = 1, 100
    error = None

    while page <= max_pages:
        items, entries, pages, ack, call_error = _call_finding_api(keyword, global_id, days, page)
        if call_error:
            error = call_error
            break
        if page == 1:
            total_entries = entries
        all_items.extend(items)
        if not items or page >= pages or pages == 0:
            break
        page += 1

    prices = [item["price"] for item in all_items if item["price"] > 0]
    return {
        "items": all_items,
        "sold_count": total_entries,
        "fetched_count": len(all_items),
        "avg_price": round(mean(prices), 2) if prices else 0,
        "median_price": round(median(prices), 2) if prices else 0,
        "min_price": round(min(prices), 2) if prices else 0,
        "max_price": round(max(prices), 2) if prices else 0,
        "prices": prices,
        "error": error,
    }


def get_sold_stats(keyword, marketplace="de", category_id=None, days=30):
    """Get comprehensive sold statistics for a keyword."""
    all_result = find_completed_items(keyword, marketplace, days)
    
    # Propagate error from find_completed_items
    if all_result.get("error"):
        return {
            "sold_count": 0,
            "fetched_count": 0,
            "avg_price": 0,
            "median_price": 0,
            "min_price": 0,
            "max_price": 0,
            "prices": [],
            "items": [],
            "by_option": {},
            "error": all_result["error"],
        }
    
    bin_items = [
        item for item in all_result["items"]
        if item["listing_type"] in ("FixedPrice", "AuctionWithBIN", "StoreInventory")
    ]
    auction_items = [item for item in all_result["items"] if item["listing_type"] == "Auction"]

    bin_prices = [i["price"] for i in bin_items if i["price"] > 0]
    auction_prices = [i["price"] for i in auction_items if i["price"] > 0]

    total_fetched = len(all_result["items"])
    total_entries = all_result["sold_count"]

    if total_fetched > 0 and total_entries > total_fetched:
        bin_ratio = len(bin_items) / total_fetched
        auction_ratio = len(auction_items) / total_fetched
        bin_count = int(total_entries * bin_ratio)
        auction_count = int(total_entries * auction_ratio)
    else:
        bin_count = len(bin_items)
        auction_count = len(auction_items)

    def _stats(prices, count):
        return {
            "sold_count": count,
            "avg_price": round(mean(prices), 2) if prices else 0,
            "median_price": round(median(prices), 2) if prices else 0,
            "min_price": round(min(prices), 2) if prices else 0,
            "max_price": round(max(prices), 2) if prices else 0,
            "prices": prices,
        }

    return {
        "sold_count": total_entries,
        "fetched_count": total_fetched,
        "avg_price": all_result["avg_price"],
        "median_price": all_result["median_price"],
        "min_price": all_result["min_price"],
        "max_price": all_result["max_price"],
        "prices": all_result["prices"],
        "items": all_result["items"],
        "by_option": {
            "FIXED_PRICE": _stats(bin_prices, bin_count),
            "AUCTION": _stats(auction_prices, auction_count),
        },
        "error": None,
    }


def batch_sold_stats(keywords, category_map=None, marketplaces=("de", "us"), days=30):
    """Calculate sold stats for multiple keywords across marketplaces."""
    results = {}
    for keyword in keywords:
        results[keyword] = {}
        for mkt in marketplaces:
            stats = get_sold_stats(keyword, mkt, None, days)
            results[keyword][mkt] = stats
    return results


if __name__ == "__main__":
    print("=== Finding API Test ===\n")
    test_keywords = ["Birkenstock Arizona", "Patagonia Nano Puff"]
    results = batch_sold_stats(test_keywords, marketplaces=("us",))
    print(f"\n=== Results ===")
    for kw, markets in results.items():
        for mkt, stats in markets.items():
            print(f"\n  {kw} ({mkt}):")
            print(f"    sold_count={stats['sold_count']}, avg=${stats['avg_price']}")
            print(f"    min=${stats['min_price']}, max=${stats['max_price']}")
            for opt, opt_stats in stats.get("by_option", {}).items():
                print(f"    {opt}: sold={opt_stats['sold_count']}, avg=${opt_stats['avg_price']}")
            if stats.get("error"):
                print(f"    ERROR: {stats['error']}")
