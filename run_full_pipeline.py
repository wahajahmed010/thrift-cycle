#!/usr/bin/env python3
"""Run the full Thrift-Cycle pipeline with all keywords."""
import sys
sys.path.insert(0, '/home/wahaj/.openclaw/workspace/thrift-cycle')
from pipeline import run_pipeline, KEYWORDS, MARKETPLACES

print(f"Running full pipeline with {len(KEYWORDS)} keywords across {len(MARKETPLACES)} marketplaces...\n")
results = run_pipeline(keywords=KEYWORDS, marketplaces=MARKETPLACES)
print(f"\n=== FINAL: {len(results)} results ===")
