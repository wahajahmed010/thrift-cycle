#!/usr/bin/env python3
"""Thrift-Cycle Report Generator — Formats pipeline output for Telegram.
"""

import json
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "thrift_cycle.db")

TELEGRAM_MAX_LEN = 4096

def format_score(emoji, keyword, marketplace, active, sold, avg_price, str_pct, sellability, trend, confidence):
    """Format a single line score."""
    return f"{emoji} **{keyword}** ({marketplace.upper()})\n  STR: {str_pct}% | Avg: €{avg_price:.0f} | {trend} | {confidence}"

def generate_report(date=None):
    """Generate a Markdown report from pipeline data.
    
    Returns list of message strings (split for Telegram length limits).
    """
    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Get today's snapshots (buying_option = 'all' for summary)
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
    
    # Group by score band
    hot = [r for r in rows if r["sellability_index"] >= 0.60]
    warm = [r for r in rows if 0.30 <= r["sellability_index"] < 0.60]
    cold = [r for r in rows if r["sellability_index"] < 0.30]
    
    # Trending up/down
    trending_up = [r for r in rows if r["trend_direction"] == "▲"]
    trending_down = [r for r in rows if r["trend_direction"] == "▼"]
    
    messages = []
    
    # Header
    header = f"📊 **Thrift-Cycle Report — {date}**\n\n"
    
    # Build sections
    sections = []
    
    if hot:
        section = "🔥 **HOT** (index ≥ 0.60)\n"
        for r in hot:
            section += f"  {r['trend_direction']} **{r['keyword']}** ({r['marketplace'].upper()})\n"
            section += f"    STR: {r['str']}% | Avg: ${r['avg_price']:.0f} | Sold: {r['sold_count']} | {r['confidence']}\n"
        sections.append(section)
    
    if warm:
        section = "🌡️ **WARM** (0.30–0.59)\n"
        for r in warm:
            section += f"  {r['trend_direction']} **{r['keyword']}** ({r['marketplace'].upper()})\n"
            section += f"    STR: {r['str']}% | Avg: ${r['avg_price']:.0f} | Sold: {r['sold_count']} | {r['confidence']}\n"
        sections.append(section)
    
    if cold:
        section = "❄️ **COLD** (< 0.30)\n"
        for r in cold[:10]:  # Top 10 cold items only
            section += f"  {r['trend_direction']} **{r['keyword']}** ({r['marketplace'].upper()})\n"
            section += f"    STR: {r['str']}% | Avg: ${r['avg_price']:.0f} | Sold: {r['sold_count']} | {r['confidence']}\n"
        if len(cold) > 10:
            section += f"  ... and {len(cold) - 10} more\n"
        sections.append(section)
    
    # Trending summary
    trend_section = f"\n📈 **Trending up:** {len(trending_up)} items\n📉 **Cooling down:** {len(trending_down)} items\n"
    
    # Split into Telegram-sized messages
    current_msg = header
    
    for section in sections:
        if len(current_msg) + len(section) + len(trend_section) > TELEGRAM_MAX_LEN:
            messages.append(current_msg.strip())
            current_msg = ""
        current_msg += section + "\n"
    
    current_msg += trend_section
    messages.append(current_msg.strip())
    
    return messages

if __name__ == "__main__":
    # Generate report from latest data
    print("=== Thrift-Cycle Report ===\n")
    messages = generate_report()
    for i, msg in enumerate(messages, 1):
        print(f"\n--- Message {i} ({len(msg)} chars) ---\n")
        print(msg)