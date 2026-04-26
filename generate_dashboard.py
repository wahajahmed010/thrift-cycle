#!/usr/bin/env python3
"""Generate dashboard data.js from existing DB results."""
import json
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "thrift_cycle.db")
DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")

def generate():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Fetch all snapshots from today (all buying_option)
    c.execute("""
        SELECT date, keyword, marketplace, active_count, sold_count,
               avg_price, str, sellability_index, confidence, trend_direction
        FROM snapshots
        WHERE buying_option = 'all' AND date = '2026-04-26'
        ORDER BY sellability_index DESC
    """)
    
    results = []
    for row in c.fetchall():
        date, keyword, marketplace, active, sold, avg_price, str_val, sell_index, confidence, trend = row
        results.append({
            "keyword": keyword,
            "marketplace": marketplace,
            "active": active,
            "sold": sold,
            "avg_price": avg_price,
            "sellability": sell_index,
            "confidence": confidence,
            "trend": trend,
            "band": "HOT" if sell_index >= 0.60 else ("WARM" if sell_index >= 0.30 else "COLD"),
        })
    
    conn.close()
    
    data = {"date": "2026-04-26", "results": results}
    os.makedirs(DOCS_DIR, exist_ok=True)
    output_path = os.path.join(DOCS_DIR, "data.js")
    
    with open(output_path, "w") as f:
        f.write("const PIPELINE_DATA = ")
        json.dump(data, f, indent=2)
        f.write(";")
    
    print(f"Wrote {len(results)} results to {output_path}")
    return results

if __name__ == "__main__":
    generate()
