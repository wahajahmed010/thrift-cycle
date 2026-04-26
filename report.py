#!/usr/bin/env python3
"""Thrift-Cycle Report Generator — Formats pipeline output for Telegram.
"""

import json
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "thrift_cycle.db")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

TELEGRAM_MAX_LEN = 4096

def load_latest_data(date=None):
    """Load pipeline data from JSON file (includes Fleek margins)."""
    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")
    
    data_file = os.path.join(DATA_DIR, f"{date}.json")
    if os.path.exists(data_file):
        with open(data_file) as f:
            return json.load(f), date
    
    return None, date

def generate_report(date=None):
    """Generate a Markdown report from pipeline data.
    
    Returns list of message strings (split for Telegram length limits).
    """
    # Try JSON data first (has Fleek margins)
    data, date = load_latest_data(date)
    
    if data:
        return generate_from_json(data, date)
    
    # Fallback to DB
    return generate_from_db(date)

def generate_from_json(data, date):
    """Generate report from pipeline JSON output (includes Fleek margins)."""
    results = data.get("results", [])
    
    if not results:
        return [f"No data for {date}. Run pipeline first."]
    
    # Separate items with and without Fleek data
    with_margin = [r for r in results if r.get("fleek_cost") and r.get("margin")]
    without_margin = [r for r in results if not r.get("fleek_cost") or not r.get("margin")]
    
    # Sort: with_margin by ROI desc, without_margin by sellability desc
    with_margin.sort(key=lambda x: x.get("roi", 0), reverse=True)
    without_margin.sort(key=lambda x: x.get("sellability", 0), reverse=True)
    
    hot = [r for r in results if r.get("band") == "HOT"]
    warm = [r for r in results if r.get("band") == "WARM"]
    cold = [r for r in results if r.get("band") == "COLD"]
    
    messages = []
    
    # Header
    header = f"📊 **Thrift-Cycle Report — {date}**\n"
    header += f"{len(results)} items | {len(with_margin)} with Fleek margins\n\n"
    
    current_msg = header
    
    # Profitable items (sorted by ROI)
    if with_margin:
        section = "\n💰 **BEST MARGINS** (by ROI)\n"
        for r in with_margin[:15]:
            mkt = r.get("marketplace", "").upper()
            trend = r.get("trend", "→")
            band = r.get("band", "COLD")
            band_emoji = {"HOT": "🔥", "WARM": "🌡️", "COLD": "❄️"}.get(band, "")
            section += f"  {band_emoji}{trend} **{r['keyword']}** ({mkt})\n"
            section += f"    Margin: €{r['margin']:.0f} | ROI: {r['roi']}% | STR: {r.get('sellability', 0)*100:.0f}%\n"
            section += f"    Sell: €{r.get('avg_price', 0):.0f} | Source: ${r.get('fleek_cost', 0):.0f}/pc\n"
        current_msg += section + "\n"
    
    # HOT items
    if hot:
        section = "🔥 **HOT** (sellability ≥ 0.60)\n"
        for r in hot:
            mkt = r.get("marketplace", "").upper()
            trend = r.get("trend", "→")
            margin_str = f" | Margin: €{r['margin']:.0f} ({r['roi']}%)" if r.get("margin") else ""
            section += f"  {trend} **{r['keyword']}** ({mkt})\n"
            section += f"    STR: {r.get('sellability', 0)*100:.0f}% | Avg: €{r.get('avg_price', 0):.0f} | Sold: {r.get('sold', 0)}{margin_str}\n"
        current_msg += section + "\n"
    
    # WARM items
    if warm:
        section = "🌡️ **WARM** (0.30–0.59)\n"
        for r in warm:
            mkt = r.get("marketplace", "").upper()
            trend = r.get("trend", "→")
            margin_str = f" | M: €{r['margin']:.0f}" if r.get("margin") else ""
            section += f"  {trend} **{r['keyword']}** ({mkt})\n"
            section += f"    STR: {r.get('sellability', 0)*100:.0f}% | Avg: €{r.get('avg_price', 0):.0f}{margin_str}\n"
        current_msg += section + "\n"
    
    # Trending
    trending_up = [r for r in results if r.get("trend") == "▲"]
    trending_down = [r for r in results if r.get("trend") == "▼"]
    
    footer = f"📈 Trending up: {len(trending_up)} | 📉 Cooling: {len(trending_down)}\n"
    
    if len(current_msg) + len(footer) > TELEGRAM_MAX_LEN:
        messages.append(current_msg.strip())
        current_msg = ""
    
    current_msg += footer
    messages.append(current_msg.strip())
    
    return messages

def generate_from_db(date):
    """Fallback: generate report from SQLite DB (no Fleek margins)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("""
        SELECT keyword, marketplace, active_count, sold_count, 
               avg_price, str, sellability_index, confidence, trend_direction
        FROM snapshots 
        WHERE date = ? AND buying_option = 'all'
        ORDER BY sellability_index DESC
    """, (date,))
    
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        return [f"No data for {date}. Run pipeline first."]
    
    hot = [r for r in rows if r["sellability_index"] >= 0.60]
    warm = [r for r in rows if 0.30 <= r["sellability_index"] < 0.60]
    cold = [r for r in rows if r["sellability_index"] < 0.30]
    
    messages = []
    current_msg = f"📊 **Thrift-Cycle Report — {date}**\n\n"
    
    if hot:
        section = "🔥 **HOT** (index ≥ 0.60)\n"
        for r in hot:
            section += f"  {r['trend_direction']} **{r['keyword']}** ({r['marketplace'].upper()})\n"
            section += f"    STR: {r['str']}% | Avg: ${r['avg_price']:.0f} | Sold: {r['sold_count']} | {r['confidence']}\n"
        current_msg += section + "\n"
    
    if warm:
        section = "🌡️ **WARM** (0.30–0.59)\n"
        for r in warm:
            section += f"  {r['trend_direction']} **{r['keyword']}** ({r['marketplace'].upper()})\n"
            section += f"    STR: {r['str']}% | Avg: ${r['avg_price']:.0f} | Sold: {r['sold_count']} | {r['confidence']}\n"
        current_msg += section + "\n"
    
    if cold:
        section = "❄️ **COLD** (top 10)\n"
        for r in cold[:10]:
            section += f"  {r['trend_direction']} **{r['keyword']}** ({r['marketplace'].upper()})\n"
            section += f"    STR: {r['str']}% | Avg: ${r['avg_price']:.0f} | Sold: {r['sold_count']} | {r['confidence']}\n"
        if len(cold) > 10:
            section += f"  ... and {len(cold) - 10} more\n"
        current_msg += section + "\n"
    
    trending_up = [r for r in rows if r["trend_direction"] == "▲"]
    trending_down = [r for r in rows if r["trend_direction"] == "▼"]
    current_msg += f"📈 Trending up: {len(trending_up)} | 📉 Cooling: {len(trending_down)}\n"
    
    messages.append(current_msg.strip())
    return messages

if __name__ == "__main__":
    print("=== Thrift-Cycle Report ===\n")
    messages = generate_report()
    for i, msg in enumerate(messages, 1):
        print(f"\n--- Message {i} ({len(msg)} chars) ---\n")
        print(msg)