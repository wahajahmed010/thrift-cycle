# Thrift-Cycle Predictor — Project Plan

> Created: 2026-04-23 | Owner: Wahaj | Status: Awaiting eBay API keys

---

## What We're Building

A tool that tells Wahaj **what used products sell fast on eBay** (DE + US) and **at what average price**. Not a SaaS — a personal reseller intelligence feed.

### Outputs
| Signal | Description |
|--------|-------------|
| **Sell-Through Rate** | % of listings that sold in 30 days — the core metric |
| **Avg Sold Price** | What buyers actually paid (not listing price) |
| **Trend Direction** | ▲ heating up / ▼ cooling down / → stable (WoW) |
| **Confidence Tag** | HIGH / MEDIUM / LOW based on sample size |

### NOT In Scope
- Sourcing cost or where to buy (Wahaj's domain)
- Profit/margin calculations
- Kleinanzeigen integration (no API)
- Real-time data (daily snapshots only)

---

## Architecture

### APIs
| API | Purpose | Budget |
|-----|---------|--------|
| **Finding API** (`findCompletedItems`) | Sold listings, prices, sold count | 2,500/day |
| **Browse API** (`search`) | Active listing counts | 2,500/day |
| **Taxonomy API** | Category ID mapping per region | ~50/month |

### Sellability Index (Revised for Reseller Use)
```
Index = (SoldUnits_30d / ActiveListings) × ConfidenceMultiplier × ListingAgePenalty
```

**Score Bands:**
- **Hot** (0.60+): Fast mover, source immediately
- **Warm** (0.30–0.60): Viable with patience
- **Cold** (0.00–0.30): Slow, risk of inventory lock-up

**Confidence Tags:**
- HIGH: 100+ sold in 30d, `total` validated
- MEDIUM: 30–99 sold
- LOW: <30 sold, treat as directional only

### Data Flow
```
Daily 06:00 UTC Cron
  ├── Browse API → Active listing counts (50 keywords × 2 markets)
  ├── Finding API → Sold listings + prices (30-day window)
  ├── Clean: dedup relists, filter by country, separate BIN/auction
  ├── Calculate: STR, Avg Sold Price, Index, Trend
  └── Store: SQLite → Output: Markdown/Telegram report
```

### Storage
- SQLite time-series DB
- `snapshots` table: daily scores per keyword/marketplace/buying_option
- `listings` table: 30-day rolling for dedup
- Retention: snapshots 365d, listings 30d

---

## Keyword Universe (v1 — 50 Terms)

### DE (28 terms)
1. Birkenstock Arizona
2. Birkenstock Boston
3. Birkenstock Gizeh
4. Birkenstock Madrid
5. Birkenstock EVA
6. Lowa Renegade GTX
7. Lowa Camino GTX
8. Meindl Bhutan
9. Meindl Ortler
10. Meindl Borneo
11. Ortlieb Back-Roller
12. Ortlieb Velocity
13. Jack Wolfskin 3in1 Jacket
14. Jack Wolfskin DNA
15. Deuter Aircontact 65+10
16. Deuter Futura
17. Vaude Brenta
18. Patagonia Retro-X Fleece
19. Patagonia Better Sweater
20. Patagonia Nano Puff
21. Arc'teryx Beta LT
22. Arc'teryx Atom LT
23. Arc'teryx Zeta SL
24. Vintage Levi's 501
25. Levi's 501 Made in USA
26. Miu Miu Ballerinas
27. Repetto Ballerinas
28. Chanel Ballerinas

### US (22 terms)
29. Birkenstock Arizona
30. Birkenstock Boston
31. Birkenstock Gizeh
32. Birkenstock EVA
33. Vintage Levi's 501 80s
34. Vintage Levi's 501 90s
35. Levi's 501 Red Line
36. Levi's 501 Shrink-to-Fit
37. Patagonia Retro-X Fleece
38. Patagonia Better Sweater
39. Patagonia Nano Puff
40. Patagonia Houdini
41. Patagonia Synchilla
42. Arc'teryx Beta LT
43. Arc'teryx Atom LT
44. Arc'teryx Alpha SV
45. Arc'teryx Zeta SL
46. Arc'teryx Gamma MX
47. Lowa Renegade GTX
48. Meindl Bhutan
49. Tory Burch Ballet Flats
50. Miu Miu Ballet Flats

---

## Seasonal Calendar (S/S 2026)

| Month | What Moves | Action |
|-------|-----------|--------|
| **Feb–Mar** | Demand starts rising | **SOURCE NOW** — best buy window before listing surge |
| **Apr–Jun** | Peak demand, pre-saturation | **SELL NOW** — Birkenstocks, ballet flats, lightweight shells |
| **Jul–Aug** | Outdoor peaks (hiking, cycling) | Lowa, Meindl, Ortlieb, Deuter move hardest |
| **May–Jun** | Festival season | Vintage Levi's, statement pieces |

**Seasonal Lag:** Listings flood 2–4 weeks AFTER demand starts. Source early, list when demand peaks.

---

## Key Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Finding API sunset (legacy XML) | Existential — no sold data | Build scraping hedge within 90 days |
| Browse API `total` unreliable | Index denominator wrong | Validate against ground truth; failover to `totalEntries` |
| Kleinanzeigen blind spot | DE market incomplete | Acknowledge; eBay.de only |
| Cross-border noise | Sold counts may reflect foreign buyers | No API fix; position as "listing liquidity" not "domestic demand" |
| Multi-variation inflation | Active count overstated | Accept as upper-bound; confidence tag reflects this |

---

## Next Steps

1. ~~**eBay Dev Program approval**~~ ✅ Approved 2026-04-26
2. **OAuth2 client credentials flow** — testing now
3. **Taxonomy API** — pre-build DE + US category ID maps for all 50 keywords
4. **Browse API integration** — active counts first (simpler endpoint)
5. **Finding API integration** — sold data + prices (XML parsing)
6. **Daily pipeline** — cron job, SQLite, Markdown report output
7. **Telegram alerts** — hot/warm score changes pushed to Wahaj

---

## Files in This Project
| File | Purpose |
|------|---------|
| `CONTEXT.md` | Wahaj's context, scope, API status |
| `research-phase1.md` | Deep research findings |
| `council-review.md` | 3-expert stress test |
| `technical-design.md` | Full architecture (655 lines) |
| `PROJECT-PLAN.md` | ← This file. Survives compaction. |