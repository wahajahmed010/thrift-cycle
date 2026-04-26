#!/usr/bin/env python3
"""eBay Taxonomy API — Category ID Mapper for Thrift-Cycle.
Maps product keywords to eBay category IDs for DE and US marketplaces.
"""

import json
import time
import urllib.request
import urllib.parse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ebay_auth import get_token

CATEGORY_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "category_map.json")

# eBay marketplace tree IDs
MARKETPLACE_TREES = {
    "de": 69,  # EBAY-DE
    "us": 0,   # EBAY-US
}

RATE_LIMIT_DELAY = 0.25  # 4 calls/sec max

def fetch_category_tree(tree_id):
    """Fetch full category tree from eBay Taxonomy API."""
    token = get_token()
    url = f"https://api.ebay.com/commerce/taxonomy/v1/category_tree/{tree_id}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Taxonomy API error ({e.code}): {body[:300]}", file=sys.stderr)
        return None

def find_categories_by_keyword(tree_data, keyword):
    """Search category tree for best matching leaf categories."""
    if not tree_data:
        return []
    
    keyword_lower = keyword.lower()
    matches = []
    
    def search_node(node, path=""):
        name = node.get("leaf_category_node_name", node.get("category", {}).get("name", ""))
        cat_id = node.get("category", {}).get("category_id", node.get("leaf_category_node_id", ""))
        
        # Check if this node matches
        if name and keyword_lower in name.lower():
            # Prefer leaf nodes
            is_leaf = node.get("leaf_category_node", True)
            matches.append({
                "category_id": str(cat_id),
                "category_name": name,
                "is_leaf": is_leaf,
                "path": f"{path} > {name}" if path else name,
                "match_score": len(keyword_lower) / max(len(name.lower()), 1),
            })
        
        # Recurse into children
        for child in node.get("child_category_tree_nodes", []):
            child_path = f"{path} > {name}" if path else name
            search_node(child, child_path)
    
    # Start from root
    root = tree_data.get("root_category_node", tree_data)
    search_node(root)
    
    # Sort: leaf nodes first, then by match score
    matches.sort(key=lambda x: (-int(x["is_leaf"]), -x["match_score"]))
    return matches

def search_category(tree_id, keyword):
    """Search for a keyword in a specific marketplace category tree."""
    tree_data = fetch_category_tree(tree_id)
    if not tree_data:
        return []
    return find_categories_by_keyword(tree_data, keyword)

def build_category_map(keywords):
    """Build category map for all keywords across DE and US marketplaces."""
    category_map = {}
    
    for marketplace, tree_id in MARKETPLACE_TREES.items():
        print(f"\n=== Fetching {marketplace.upper()} category tree (tree_id={tree_id}) ===")
        tree_data = fetch_category_tree(tree_id)
        time.sleep(RATE_LIMIT_DELAY)
        
        if not tree_data:
            print(f"  Failed to fetch {marketplace.upper()} tree")
            continue
        
        total_categories = tree_data.get("root_category_node", {}).get("leaf_category_node_count", "?")
        print(f"  Tree loaded. Total leaf categories: {total_categories}")
        
        for keyword in keywords:
            if keyword not in category_map:
                category_map[keyword] = {}
            
            matches = find_categories_by_keyword(tree_data, keyword)
            if matches:
                best = matches[0]
                category_map[keyword][marketplace] = {
                    "category_id": best["category_id"],
                    "category_name": best["category_name"],
                    "path": best["path"],
                    "all_matches": len(matches),
                }
                print(f"  ✓ {keyword} → {best['category_name']} ({best['category_id']}) [{len(matches)} matches]")
            else:
                print(f"  ✗ {keyword} → no match found")
                category_map[keyword][marketplace] = None
            
            time.sleep(RATE_LIMIT_DELAY)
    
    # Save
    with open(CATEGORY_MAP_PATH, "w") as f:
        json.dump(category_map, f, indent=2)
    print(f"\nCategory map saved to {CATEGORY_MAP_PATH}")
    return category_map

# All 50 keywords from PROJECT-PLAN.md
ALL_KEYWORDS = [
    # DE (28 terms)
    "Birkenstock Arizona", "Birkenstock Boston", "Birkenstock Gizeh", "Birkenstock Madrid",
    "Birkenstock EVA", "Lowa Renegade GTX", "Lowa Camino GTX", "Meindl Bhutan",
    "Meindl Ortler", "Meindl Borneo", "Ortlieb Back-Roller", "Ortlieb Velocity",
    "Jack Wolfskin 3in1 Jacket", "Jack Wolfskin DNA", "Deuter Aircontact 65+10",
    "Deuter Futura", "Vaude Brenta", "Patagonia Retro-X Fleece", "Patagonia Better Sweater",
    "Patagonia Nano Puff", "Arc'teryx Beta LT", "Arc'teryx Atom LT", "Arc'teryx Zeta SL",
    "Vintage Levi's 501", "Levi's 501 Made in USA", "Miu Miu Ballerinas", "Repetto Ballerinas",
    "Chanel Ballerinas",
    # US (22 terms, some overlap with DE)
    "Vintage Levi's 501 80s", "Vintage Levi's 501 90s", "Levi's 501 Red Line",
    "Levi's 501 Shrink-to-Fit", "Patagonia Houdini", "Patagonia Synchilla",
    "Arc'teryx Alpha SV", "Arc'teryx Gamma MX", "Tory Burch Ballet Flats",
    "Miu Miu Ballet Flats",
]

if __name__ == "__main__":
    print("=== Thrift-Cycle Category Mapper ===\n")
    
    # Check if category map already exists
    if os.path.exists(CATEGORY_MAP_PATH):
        print(f"Existing category map found at {CATEGORY_MAP_PATH}")
        with open(CATEGORY_MAP_PATH) as f:
            existing = json.load(f)
        print(f"  {len(existing)} keywords already mapped")
        action = input("Rebuild? (y/N): ").strip().lower()
        if action != "y":
            print("Using existing map.")
            for kw, markets in existing.items():
                for mkt, info in (markets or {}).items():
                    if info:
                        print(f"  {kw} ({mkt}): {info['category_name']} [{info['category_id']}]")
            sys.exit(0)
    
    # Build fresh
    category_map = build_category_map(ALL_KEYWORDS)
    
    # Summary
    mapped = sum(1 for kw, markets in category_map.items() if any(v for v in (markets or {}).values()))
    print(f"\n=== Summary ===")
    print(f"Mapped: {mapped}/{len(ALL_KEYWORDS)} keywords")
    print(f"Missing: {len(ALL_KEYWORDS) - mapped} keywords")