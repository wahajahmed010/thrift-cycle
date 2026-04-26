# Thrift-Cycle Predictor

Personal reseller intelligence tool for eBay DE + US markets. Tells you **what used products sell fast** and **at what average price** — not where to source or how to calculate profit.

## What It Outputs

| Signal | Description |
|--------|-------------|
| **Sell-Through Rate** | % of listings that sold in 30 days |
| **Avg Sold Price** | What buyers actually paid |
| **Trend Direction** | ▲ heating up / ▼ cooling down / → stable |
| **Confidence Tag** | HIGH / MEDIUM / LOW based on sample size |

## Architecture

- **Browse API** — Active listing counts, buying option breakdowns, condition distributions, price samples
- **Sold Data Scraper** — Completed/sold listing prices from eBay's public pages (Finding API is deprecated)
- **Pipeline** — Daily orchestrator that calculates sellability index and trends
- **Report** — Telegram-friendly Markdown report generator

## Setup

1. Get eBay Developer credentials from https://developer.ebay.com/
2. Save to `~/.openclaw/.ebay_credentials`:
   ```json
   {"app_id": "...", "cert_id": "...", "dev_id": "..."}
   ```
3. Run the pipeline:
   ```bash
   python3 pipeline.py
   ```
4. Generate report:
   ```bash
   python3 report.py
   ```

## Modules

| File | Purpose |
|------|---------|
| `ebay_auth.py` | OAuth2 token manager (client credentials flow) |
| `browse_api.py` | eBay Browse API — active counts, prices, distributions |
| `finding_api.py` | Sold data via web scraping (Finding API deprecated) |
| `taxonomy.py` | Category ID mapper (50 keywords → eBay categories) |
| `pipeline.py` | Daily pipeline — calculates STR, sellability index, trends |
| `report.py` | Telegram-formatted report generator |

## Keyword Coverage

50 keywords across DE (28) and US (22) markets: Birkenstock, Lowa, Meindl, Ortlieb, Jack Wolfskin, Deuter, Vaude, Patagonia, Arc'teryx, Levi's, Miu Miu, Repetto, Chanel, Tory Burch.

## License

MIT