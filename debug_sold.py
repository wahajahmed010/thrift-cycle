#!/usr/bin/env python3
"""Debug: Check what eBay's sold listings page actually returns."""
import urllib.request
import urllib.parse
import re
import os

keyword = "Birkenstock Arizona"
url = f"https://www.ebay.com/sch/i.html?LH_Sold=1&LH_Complete=1&_nkw={urllib.parse.quote(keyword)}"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=15) as resp:
    html = resp.read().decode("utf-8", errors="replace")

# Save first 50K for analysis
debug_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_sold_page.html")
with open(debug_path, "w") as f:
    f.write(html[:50000])

print(f"Saved {min(len(html), 50000)} chars to {debug_path}")

# Search for total count patterns
patterns = [
    r'"totalItems"\s*:\s*"?(\d+)"?',
    r'(\d[\d,]*)\s*(?:results?|Ergebnisse?|items?|listings?)',
    r'class="srp-controls__count-heading[^"]*">[^<]*(\d[\d,]*)',
    r'data-totalcount="(\d+)"',
    r'(\d[\d,]+)\s+sold',
    r'"total"\s*:\s*(\d+)',
]

for p in patterns:
    match = re.search(p, html, re.IGNORECASE)
    if match:
        print(f"Pattern matched: {p[:50]}... → {match.group(1)}")
    else:
        print(f"No match: {p[:50]}...")

# Check for JSON data in script tags
json_matches = re.findall(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', html)
if json_matches:
    print(f"\nFound __INITIAL_STATE__ JSON ({len(json_matches[0])} chars)")
    
# Check for any "sold" text
sold_mentions = re.findall(r'(?:sold|Sold|SOLD)[^<]{0,50}', html[:20000])
for m in sold_mentions[:5]:
    print(f"Sold mention: {m[:80]}")