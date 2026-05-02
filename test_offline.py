#!/usr/bin/env python3
"""Quick offline test of the Thrift-Cycle pipeline modules."""
import sys, os, sqlite3
sys.path.insert(0, '/home/wahaj/.openclaw/workspace/thrift-cycle')

print("=== Offline Module Tests ===\n")

# 1. ebay_auth
print("1. ebay_auth...")
from ebay_auth import load_credentials
app_id, cert_id, dev_id = load_credentials()
print(f"   Credentials loaded (app_id starts with: {app_id[:6]}...)")

# 2. taxonomy
print("\n2. taxonomy...")
from taxonomy import MARKETPLACE_TREES, ALL_KEYWORDS, search_categories
assert len(ALL_KEYWORDS) == 38, f"Expected 38 keywords, got {len(ALL_KEYWORDS)}"
print(f"   Keywords: {len(ALL_KEYWORDS)}")
print(f"   Trees: {MARKETPLACE_TREES}")

# 3. browse_api
print("\n3. browse_api...")
from browse_api import get_active_counts, batch_active_counts, MARKETPLACES
assert MARKETPLACES == {"de": "EBAY-DE", "us": "EBAY-US"}
print(f"   Marketplaces: {MARKETPLACES}")

# 4. finding_api
print("\n4. finding_api...")
from finding_api import _parse_finding_response, GLOBAL_IDS, FINDING_URL
assert "svcs.ebay.com" in FINDING_URL
print(f"   FINDING_URL: {FINDING_URL}")
print(f"   GLOBAL_IDS: {GLOBAL_IDS}")

# 5. pipeline
print("\n5. pipeline...")
from pipeline import init_db, calculate_metrics, KEYWORDS_DE, KEYWORDS_US
assert len(KEYWORDS_DE) == 28
assert len(KEYWORDS_US) == 22
print(f"   DE keywords: {len(KEYWORDS_DE)}, US: {len(KEYWORDS_US)}")

# Test metrics
calc = calculate_metrics(50, 500)
assert calc["str"] == 9.1
assert calc["confidence"] == "MEDIUM"
print(f"   Metrics test: str={calc['str']}%, index={calc['index_final']}, conf={calc['confidence']}")

# Test DB init
init_db()
DB = '/home/wahaj/.openclaw/workspace/thrift-cycle/thrift_cycle.db'
conn = sqlite3.connect(DB)
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
assert 'snapshots' in tables
assert 'listings' in tables
conn.close()
print(f"   DB tables: {tables}")

# 6. report
print("\n6. report...")
from report import generate_report, _chunk_messages, TELEGRAM_MAX_LEN
assert TELEGRAM_MAX_LEN == 4096
print(f"   Telegram limit: {TELEGRAM_MAX_LEN}")

msgs = generate_report('2099-01-01')
assert len(msgs) > 0
print(f"   Empty report: {len(msgs)} msg(s)")

# 7. XML parsing
print("\n7. XML parsing...")
sample_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<findCompletedItemsResponse xmlns="http://www.ebay.com/marketplace/search/v1/services">
  <ack>Success</ack>
  <searchResult count="2">
    <item>
      <itemId>123</itemId>
      <title>Test Birkenstock</title>
      <sellingStatus>
        <currentPrice currencyId="USD">45.00</currentPrice>
        <sellingState>EndedWithSales</sellingState>
      </sellingStatus>
      <listingInfo>
        <listingType>FixedPrice</listingType>
        <endTime>2026-04-20T12:00:00.000Z</endTime>
      </listingInfo>
      <condition><conditionId>3000</conditionId></condition>
    </item>
  </searchResult>
  <paginationOutput>
    <totalEntries>1</totalEntries>
    <totalPages>1</totalPages>
  </paginationOutput>
</findCompletedItemsResponse>'''
items, total, pages, ack, err = _parse_finding_response(sample_xml)
assert ack == 'Success'
assert total == 1
assert len(items) == 1
assert items[0]['price'] == 45.0
print(f"   XML parse: items={len(items)}, total={total}, price=${items[0]['price']}")

print("\n=== ALL OFFLINE TESTS PASSED ===")
