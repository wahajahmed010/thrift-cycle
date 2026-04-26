#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/wahaj/.openclaw/workspace/thrift-cycle')
from pipeline import run_pipeline, KEYWORDS, MARKETPLACES

results = run_pipeline(keywords=KEYWORDS, marketplaces=MARKETPLACES)
print(f"\nTotal results: {len(results)}")
