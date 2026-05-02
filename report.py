#!/usr/bin/env python3
"""Thrift-Cycle Telegram Report Generator.

Formats pipeline output as Telegram-friendly Markdown.
Sections: 🔥 Hot Movers, 📈 Trending Up, ➡️ Stable, 📉 Cooling Down
"""

import json
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "thrift_cycle.db")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

TELEGRAM_MAX_LEN = 4096
HOT_THRESHOLD = 0.60
WARM_THRESHOLD = 0.30


def load_latest_data(date=None):
    """Load pipeline JSON output for a date."""
    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")
    data_file = os.path.join(DATA_DIR, f"{date}.json")
    if os.path.exists(data_file):
        with open(data_file) as f:
            return json.load(f), date
    return None, date


def _format_row(r):
    """Format a single keyword row for Telegram."""
    keyword = r["keyword"]
    mkt = r["marketplace"].upper()
    str_pct = r.get("str", 0) or (r.get("sellability", 0) * 100)
    avg_price = r.get("avg_price", 0)
    trend = r.get("trend", "→")
    conf = r.get("confidence", "LOW")

    # Trend arrow
    trend_icon = {"▲": "📈", "▼": "📉", "→": "➡️"}.get(trend, "➡️")

    # Confidence emoji
    conf_emoji = {
        "HIGH": "🟢",
        "MEDIUM": "🟡",
        "LOW": "🔴",
    }.get(conf, "🔴")

    return (
        f"{trend_icon} *{keyword}* ({mkt})\n"
        f"   STR: `{str_pct:.1f}%` | Avg: `${avg_price:.0f}` | {conf_emoji} {conf}"
    )


def _chunk_messages(lines, header="", max_len=TELEGRAM_MAX_LEN):
    """Split lines into chunks that fit Telegram limit."""
    messages = []
    current = header
    for line in lines:
        # +1 for newline
        if len(current) + len(line) + 1 > max_len:
            messages.append(current.strip())
            current = line
        else:
            current += "\n" + line
    if current:
        messages.append(current.strip())
    return messages


def generate_report(date=None):
    """Generate Telegram-friendly Markdown report.

    Returns list of message strings (split for length limit).
    """
    data, date = load_latest_data(date)

    if data:
        return _generate_from_json(data, date)
    return _generate_from_db(date)


def _generate_from_json(data, date):
    results = data.get("results", [])
    if not results:
        return [f"📊 *Thrift-Cycle — {date}*\n\nNo data today."]

    # Split by band
    hot = [r for r in results if r.get("sellability", 0) >= HOT_THRESHOLD]
    warm = [r for r in results if WARM_THRESHOLD <= r.get("sellability", 0) < HOT_THRESHOLD]
    cold = [r for r in results if r.get("sellability", 0) < WARM_THRESHOLD]

    # Sort by sellability desc
    hot.sort(key=lambda x: x.get("sellability", 0), reverse=True)
    warm.sort(key=lambda x: x.get("sellability", 0), reverse=True)
    cold.sort(key=lambda x: x.get("sellability", 0), reverse=True)

    # Build sections
    lines = []

    # 🔥 Hot Movers
    if hot:
        lines.append(f"\n🔥 *HOT MOVERS* ({len(hot)})")
        for r in hot:
            lines.append(_format_row(r))

    # 📈 Trending Up
    trending_up = [r for r in results if r.get("trend") == "▲"]
    if trending_up:
        lines.append(f"\n📈 *TRENDING UP* ({len(trending_up)})")
        for r in trending_up:
            lines.append(_format_row(r))

    # ➡️ Stable
    stable = [r for r in results if r.get("trend") == "→"]
    if stable:
        # Only show top 10 stable to keep it concise
        lines.append(f"\n➡️ *STABLE* ({len(stable)} total, top 10)")
        for r in stable[:10]:
            lines.append(_format_row(r))

    # 📉 Cooling Down
    cooling = [r for r in results if r.get("trend") == "▼"]
    if cooling:
        lines.append(f"\n📉 *COOLING DOWN* ({len(cooling)})")
        for r in cooling:
            lines.append(_format_row(r))

    # Footer
    footer = (
        f"\n📊 *Thrift-Cycle — {date}*\n"
        f"{len(results)} keyword-market combos | "
        f"🔥 {len(hot)} hot | "
        f"📈 {len(trending_up)} up | "
        f"📉 {len(cooling)} down"
    )

    header = f"📊 *Thrift-Cycle — {date}*\n"
    return _chunk_messages(lines, header)


def _generate_from_db(date):
    """Fallback: generate from SQLite DB."""
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
        return [f"📊 *Thrift-Cycle — {date}*\n\nNo data today."]

    results = []
    for r in rows:
        results.append({
            "keyword": r["keyword"],
            "marketplace": r["marketplace"],
            "str": r["str"],
            "avg_price": r["avg_price"],
            "sellability": r["sellability_index"],
            "confidence": r["confidence"],
            "trend": r["trend_direction"] or "→",
        })

    return _generate_from_json({"results": results}, date)


if __name__ == "__main__":
    print("=== Thrift-Cycle Report ===\n")
    messages = generate_report()
    for i, msg in enumerate(messages, 1):
        print(f"\n--- Message {i} ({len(msg)} chars) ---\n")
        print(msg)
