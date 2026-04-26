#!/usr/bin/env python3
import sys, json, os
sys.path.insert(0, '/home/wahaj/.openclaw/workspace/thrift-cycle')
from pipeline import run_pipeline, KEYWORDS, MARKETPLACES

print(f"Running full pipeline with {len(KEYWORDS)} keywords...")
results = run_pipeline(keywords=KEYWORDS, marketplaces=MARKETPLACES)
print(f"\n=== FINAL: {len(results)} results ===")

# Generate dashboard data
data = {'date': '2026-04-26', 'results': results}
output = '/home/wahaj/.openclaw/workspace/thrift-cycle/docs/data.js'
os.makedirs(os.path.dirname(output), exist_ok=True)
with open(output, 'w') as f:
    f.write('const PIPELINE_DATA = ')
    json.dump(data, f, indent=2)
    f.write(';')
print(f'Wrote {len(results)} results to data.js')
