# Thrift-Cycle Predictor — Technical Design

> Version: 1.0 | Date: 2026-04-23 | Status: Council Conditional GO

---

## 1. Executive Summary

### What We're Building
The **Thrift-Cycle Predictor** is a directional signal engine that scores how "sellable" specific used/thrifted products are on eBay right now. It answers one question for resellers: *"If I source this item today, how likely is it to move within 30 days?"*

### Core Value Proposition
- **Volume-focused, not margin-focused.** We measure liquidity (sell-through velocity), not profit potential.
- **Seasonally aware.** Scores are contextualized against Spring/Summer demand cycles.
- **Confidence-first.** Every score carries a confidence tag; low-data scores are surfaced, not hidden.

### Scope
| Dimension | Boundaries |
|-----------|------------|
| **Markets** | eBay Germany (EBAY_DE) + eBay US (EBAY_US) |
| **Season** | Spring/Summer 2026 (focus window: April–August) |
| **Product type** | Used / pre-owned / thrifted goods only |
| **Excluded** | New items, Kleinanzeigen (no API), non-eBay platforms |

### Why eBay
- Largest structured used-goods marketplace in both target regions.
- Official APIs exist for active inventory (Browse API) and completed transactions (Finding API).
- No other platform offers comparable programmatic access at this scale.

---

## 2. Sellability Index — Final Scoring Logic

### 2.1 Base Formula

```
Index_raw = (SoldUnits_30d / ActiveListings) × ΔDemand
```

| Component | Source | Description |
|-----------|--------|-------------|
| `SoldUnits_30d` | Finding API `findCompletedItems` + `SoldItemsOnly` | Count of sold listings in the last 30 days |
| `ActiveListings` | Browse API `search` → `total` | Approximate active listing count |
| `ΔDemand` | Local time-series cache | Week-over-week change in `SoldUnits_7d` |

### 2.2 Council-Mandated Adjustments

#### A. Marketplace Separation
Indices are **never blended across marketplaces.**
- `Index_DE` = score for EBAY_DE only
- `Index_US` = score for EBAY_US only

#### B. Buying-Option Separation
Each keyword gets **two parallel indices**:
- `Index_BIN` — `buyingOptions:{FIXED_PRICE}` only
- `Index_Auction` — `buyingOptions:{AUCTION}` only

Blended scores are prohibited. Auction sell-through and BIN sell-through measure different buyer behaviors.

#### C. Confidence Weighting
A sample-size penalty reduces the raw index when data is thin:

```
ConfidenceMultiplier = min(1.0, SoldUnits_30d / 30)
```

| SoldUnits_30d | Multiplier | Confidence Tag |
|---------------|------------|----------------|
| ≥ 100 | 1.00 | HIGH |
| 30–99 | 0.75 | MEDIUM |
| < 30 | SoldUnits_30d / 30 | LOW |

#### D. Price-Decay Factor
Older active listings are less representative of current liquidity. Apply a listing-age decay:

```
ListingAgePenalty = 1 - (AvgListingAge_days / 90)
```

Capped at 0 (no negative penalty). `AvgListingAge` is estimated from a sample of result items' `itemCreationDate`. This penalizes stale inventory pools.

### 2.3 Final Revised Formula

```
Index_final = Index_raw × ConfidenceMultiplier × ListingAgePenalty
```

Expanded:
```
Index_final = (SoldUnits_30d / ActiveListings) × ΔDemand × min(1.0, SoldUnits_30d / 30) × (1 - min(1.0, AvgListingAge_days / 90))
```

### 2.4 Score Bands

| Band | Range | Interpretation |
|------|-------|----------------|
| **Cold** | 0.00 – 0.30 | Low liquidity. High risk of inventory lock-up. |
| **Warm** | 0.30 – 0.60 | Moderate liquidity. Viable with patience or price flexibility. |
| **Hot** | 0.60 – 1.00+ | Strong liquidity. Fast sell-through expected. |

> Scores can exceed 1.0 if ΔDemand > 1.0 and all other factors align. Cap display at 1.0 for readability; store raw value.

### 2.5 Confidence Tags — Detailed Rules

Confidence tags reflect **data quality**, not index magnitude.

| Tag | Trigger Conditions | Display Behavior |
|-----|-------------------|------------------|
| **HIGH** | SoldUnits_30d ≥ 100 AND ActiveListings ≥ 500 AND Browse API `total` manually validated within ±25% | Full trust. Score shown without disclaimer. |
| **MEDIUM** | SoldUnits_30d 30–99 OR ActiveListings 100–499 OR `total` not yet validated | Score shown with "Medium confidence — validate before sourcing" label. |
| **LOW** | SoldUnits_30d < 30 OR ActiveListings < 100 OR `total` known to diverge >25% | Score shown with "Low confidence — insufficient data" label. Trend arrows suppressed. |

---

## 3. Data Architecture

### 3.1 API Inventory

| API | Purpose | Status | Daily Budget |
|-----|---------|--------|-------------|
| **Finding API** | Sold data (`findCompletedItems`) | ⚠️ Legacy XML, maintenance mode | 2,500 calls |
| **Browse API** | Active listings (`search` → `total`) | ✅ Active REST API | 2,500 calls |
| **Taxonomy API** | Per-region category ID resolution | ✅ Active | ~50 calls/month |

> Total combined budget: 5,000 calls/day (Finding + Browse). Taxonomy calls are negligible.

### 3.2 Daily Snapshot Pipeline

```
06:00 UTC — Pipeline start
  ├── 06:00–06:30 — Browse API: Fetch active listing totals for all 50 keywords (DE + US)
  ├── 06:30–07:30 — Finding API: Fetch sold listings (30-day window) for all 50 keywords
  ├── 07:30–07:45 — Data cleaning: Deduplication, cross-border filtering, relist flagging
  ├── 07:45–08:00 — Index calculation: Apply formula, assign confidence tags
  └── 08:00 — Write to time-series DB
```

### 3.3 Local Time-Series Database

**Storage: SQLite** (sufficient for 50 keywords × 2 markets × 2 buying options = 200 time series).

**Schema (logical):**

| Table | Key Fields |
|-------|-----------|
| `snapshots` | `date`, `marketplace`, `keyword`, `buying_option`, `sold_units_7d`, `sold_units_30d`, `active_listings`, `avg_listing_age_days`, `delta_demand`, `index_raw`, `index_final`, `confidence_tag` |
| `listings` | `item_id`, `snapshot_date`, `marketplace`, `keyword`, `title`, `price`, `condition_id`, `buying_option`, `item_location`, `is_relist`, `end_time` |
| `validation_log` | `date`, `keyword`, `marketplace`, `browse_api_total`, `manual_count`, `divergence_pct`, `action_taken` |

**Retention:**
- `snapshots`: 365 days (full year for seasonal comparison)
- `listings`: 30 days (rolling; used for deduplication and relist detection)
- `validation_log`: 90 days

### 3.4 Rate Budget Allocation (5,000 calls/day)

| Task | Calls | Notes |
|------|-------|-------|
| Browse API active totals | ~100 | 50 keywords × 2 markets |
| Browse API pagination (validation sample) | ~400 | 20 keywords × 10 pages × 2 markets |
| Finding API sold data | ~2,000 | 50 keywords × 2 markets × ~20 calls (pagination) |
| Finding API active count (failover) | ~1,500 | Reserved for `total` failover |
| Buffer / retries | ~1,000 | Absorbs rate-limit pauses |

---

## 4. Data Cleaning Strategy

### 4.1 Multi-Variation Listings

**Problem:** One parent listing with 10 size variations inflates `total` by ~10×. A single sold variation counts as one sale.

**Mitigation:**
- **Do not** attempt aspect-filter explosion (size × color × condition). At 50 keywords, this would consume the entire 5K/day budget on a single snapshot.
- **Instead:** Accept `total` as an **upper-bound estimate**. Flag keywords known to have high variation depth (e.g., "Birkenstock Arizona") in metadata.
- **Browse API filter:** Apply `aspect_filter` only for **one dominant aspect** per keyword (e.g., condition) to reduce inflation by ~2–3× without combinatorial explosion.

### 4.2 Auction vs BIN Separation

**Problem:** Auction prices are 20–40% below BIN. Blending them destroys price signal and sell-through comparability.

**Mitigation:**
- All queries are bifurcated by `buyingOptions` filter:
  - `filter=buyingOptions:{FIXED_PRICE}` → BIN index
  - `filter=buyingOptions:{AUCTION}` → Auction index
- `BEST_OFFER` listings appear under BIN in Browse API; Finding API does not expose accepted-offer flag. Treat these as BIN for index purposes.

### 4.3 Condition Variance Within "Used"

**Problem:** Condition ID `3000` ("Used") spans "like new" to "heavily worn."

**Mitigation:**
- Narrow to `conditionIds:4000` (Very Good) and `conditionIds:5000` (Good) where sample size permits.
- If `SoldUnits_30d` drops below 10 after filtering, relax to full `USED` and downgrade confidence tag to LOW.
- Store `condition_id` in time-series DB for post-hoc analysis.

### 4.4 Seasonal Lag Correction

**Problem:** Sellers flood the market 4–6 weeks after demand starts rising, temporarily depressing the sell-through ratio.

**Mitigation:**
- Normalize `ActiveListings` against a **90-day rolling average** instead of absolute count:
  ```
  AdjustedActiveListings = ActiveListings_today × (1 / (ActiveListings_today / AvgActiveListings_90d))
  ```
- If today's active count is 50% above the 90-day average, the denominator is adjusted downward to compensate for supply surge.

### 4.5 International / Cross-Border Contamination

**Problem:** Listings from China or other regions pollute domestic market signals.

**Mitigation:**
- **Browse API:** `filter=itemLocationCountry:DE` (or `US`)
- **Finding API:** `itemFilter name=LocatedIn value=DE` (or `US`)
- Acknowledge limitation: Buyer may still be cross-border (see §8). Location filter only constrains seller location.

### 4.6 Relisted Item Deduplication

**Problem:** Unsold items relisted appear as "new" listings but are stale inventory.

**Mitigation:**
- **Finding API limitation:** `itemOriginDate` is not exposed. Full relist detection is **not implementable** via official API.
- **Partial mitigation:** Track `itemId` across 30-day rolling window. If an `itemId` reappears in active listings after appearing in completed (unsold) results, flag as relist in metadata.
- **Impact:** Accept that relist detection is heuristic, not deterministic. Document this in confidence tagging.

### 4.7 Browse API `total` Validation

**Problem:** eBay explicitly warns `total` is approximate and unreliable.

**Mitigation (Council Condition #5):**
- **Week 1–2:** For 20 keywords (40% of universe), paginate through all results and count manually. Compare to `total`.
- **Divergence thresholds:**
  - `< 25% divergence`: `total` approved for production use.
  - `25–50% divergence`: Apply scaling factor to `total` for that keyword; downgrade confidence.
  - `> 50% divergence`: Blacklist `total` for that keyword; failover to Finding API `findItemsAdvanced` → `totalEntries`.
- **Ongoing:** Re-validate 5 keywords per week on a rotating basis.

### 4.8 `total` Failover Design (Council Condition #7)

If Browse API `total` diverges >30% from ground truth:
1. Switch active-count source to **Finding API `findItemsAdvanced`** → `totalEntries`.
2. `totalEntries` is more stable (exact count, not estimate) but Finding API is deprecated.
3. Log failover in `validation_log`.
4. Alert operator to investigate keyword-specific data quality.

---

## 5. Regional Heatmap Mockup

### 5.1 DE Heatmap (Spring/Summer 2026)

```
┌────────────────────────────┬─────────┬────────┬────────────┬──────────┐
│ Brand/Keyword              │ Market  │ Index  │ Confidence │ Trend    │
├────────────────────────────┼─────────┼────────┼────────────┼──────────┤
│ Birkenstock Boston         │ DE      │ 0.82   │ HIGH       │ ▲ +12%   │
│ Birkenstock Arizona        │ DE      │ 0.71   │ HIGH       │ ▲ +8%    │
│ Lowa Renegade GTX          │ DE      │ 0.65   │ MEDIUM     │ ▲ +15%   │
│ Meindl Bhutan              │ DE      │ 0.48   │ MEDIUM     │ →  +2%   │
│ Ortlieb Back-Roller        │ DE      │ 0.55   │ LOW        │ ▲ +22%   │
│ Jack Wolfskin 3in1 Jacket  │ DE      │ 0.38   │ LOW        │ ▼ -5%    │
│ Deuter Aircontact 65+10    │ DE      │ 0.41   │ LOW        │ →  +1%   │
│ Patagonia Better Sweater   │ DE      │ 0.33   │ MEDIUM     │ ▲ +6%    │
│ Arc'teryx Beta LT          │ DE      │ 0.28   │ LOW        │ ▲ +4%    │
│ Vintage Levi's 501 (DE)    │ DE      │ 0.19   │ LOW        │ →  -1%   │
└────────────────────────────┴─────────┴────────┴────────────┴──────────┘
```

### 5.2 US Heatmap (Spring/Summer 2026)

```
┌────────────────────────────┬─────────┬────────┬────────────┬──────────┐
│ Brand/Keyword              │ Market  │ Index  │ Confidence │ Trend    │
├────────────────────────────┼─────────┼────────┼────────────┼──────────┤
│ Birkenstock Arizona        │ US      │ 0.88   │ HIGH       │ ▲ +18%   │
│ Birkenstock Boston         │ US      │ 0.74   │ HIGH       │ ▲ +9%    │
│ Vintage Levi's 501 80s/90s │ US      │ 0.67   │ HIGH       │ ▲ +11%   │
│ Patagonia Retro-X Fleece   │ US      │ 0.52   │ MEDIUM     │ ▲ +7%    │
│ Arc'teryx Beta LT          │ US      │ 0.61   │ MEDIUM     │ ▲ +14%   │
│ Arc'teryx Atom LT          │ US      │ 0.44   │ MEDIUM     │ ▲ +5%    │
│ Patagonia Better Sweater   │ US      │ 0.39   │ MEDIUM     │ →  +3%   │
│ Lowa Renegade GTX          │ US      │ 0.31   │ LOW        │ ▲ +8%    │
│ Meindl Ortler              │ US      │ 0.12   │ LOW        │ →  +1%   │
│ Ortlieb Velocity           │ US      │ 0.15   │ LOW        │ ▼ -3%    │
└────────────────────────────┴─────────┴────────┴────────────┴──────────┘
```

### 5.3 Seasonal Lag Visualization

```
Demand Curve vs Listing Curve (Birkenstock Arizona, DE)
│
│     Demand ▲
│           /\
│          /  \
│         /    \
│        /      \
│       /   Listing ▲
│      /            \
│     /              \
│    /                \
│___/__________________\_____ Time
│  Apr   May   Jun   Jul   Aug
│
│ Lag = ~3 weeks: Listings peak after demand has already climbed.
│ Best sourcing window: Feb–Mar (before listing surge).
│ Best selling window: Apr–Jun (peak demand, pre-saturation).
```

### 5.4 Notes on DE-Specific Brands

| Brand | DE Context | US Context |
|-------|-----------|------------|
| **Jack Wolfskin** | Massive domestic volume; "3in1" jackets are staple. Low DE confidence due to high variation depth. | Invisible. Do not track in US universe. |
| **Deuter** | Strong backpack resale; Aircontact series moves in S/S. | Niche; low volume but high margin. |
| **Lowa / Meindl** | Core hiking brands. Renegade GTX is velocity leader. | Niche. DE-focused tracking. |
| **Ortlieb** | Cyclist seasonality (May–Sep). Back-Roller is volume driver. | Tiny market; treat as LOW confidence. |

---

## 6. API Integration Details

### 6.1 eBay Finding API (XML/SOAP)

**Endpoint:** `https://svcs.ebay.com/services/search/FindingService/v1`

**Primary call:** `findCompletedItems`

```xml
<findCompletedItemsRequest xmlns="http://www.ebay.com/marketplace/search/v1/services">
  <keywords>Birkenstock Arizona</keywords>
  <itemFilter>
    <name>SoldItemsOnly</name>
    <value>true</value>
  </itemFilter>
  <itemFilter>
    <name>Condition</name>
    <value>3000</value>
  </itemFilter>
  <itemFilter>
    <name>ListingType</name>
    <value>FixedPrice</value>
  </itemFilter>
  <itemFilter>
    <name>EndTimeFrom</name>
    <value>2026-03-24T00:00:00.000Z</value>
  </itemFilter>
  <itemFilter>
    <name>EndTimeTo</name>
    <value>2026-04-23T00:00:00.000Z</value>
  </itemFilter>
  <paginationInput>
    <entriesPerPage>100</entriesPerPage>
    <pageNumber>1</pageNumber>
  </paginationInput>
</findCompletedItemsRequest>
```

**Key response fields:**
- `searchResult.@count` — items on this page
- `searchResult.item[]` — array of listing objects
  - `sellingStatus.currentPrice` — final price
  - `listingInfo.endTime` — listing end date (used as proxy for sale date)
  - `listingInfo.listingType` — `FixedPrice` or `Auction`
  - `condition.conditionId` — numeric condition code
  - `shippingInfo.shipToLocations` / `itemLocation` — for cross-border checks
- `paginationOutput.totalEntries` — total matching results (exact count)

**Known Issues & Handling:**
| Issue | Handling |
|-------|----------|
| Returns active auctions mixed with completed | Post-filter by `listingInfo.endTime` < now; flag anomalies |
| `SoldItemsOnly` inconsistently applied | Treat `sellingStatus.sellingState` == `EndedWithSales` as authoritative; discard `EndedWithoutSales` |
| Sale date is listing end date, not transaction date | Accept as limitation; document in confidence tagging |

### 6.2 Browse API (REST/JSON)

**Endpoint:** `GET https://api.ebay.com/buy/browse/v1/item_summary/search`

**Headers:**
```
Authorization: Bearer <token>
X-EBAY-C-MARKETPLACE-ID: EBAY_DE   (or EBAY_US)
```

**Query parameters:**
```
q=Birkenstock+Arizona
filter=buyingOptions:{FIXED_PRICE}
filter=conditions:{USED}
filter=itemLocationCountry:DE
limit=200
offset=0
```

**Key response fields:**
- `total` — **approximate** active listing count (⚠️ unreliable per eBay)
- `itemSummaries[]` — array of items
  - `price.value` — current price
  - `condition` — condition string + ID
  - `buyingOptions[]` — `FIXED_PRICE`, `AUCTION`, `BEST_OFFER`
  - `itemLocation.country` — seller location
  - `itemCreationDate` — listing creation date

**Pagination Strategy:**
- Max page size: 200
- Max result set: 10,000 items
- For validation sampling: iterate through pages with `offset` increments of 200.
- For production active counts: use `total` from page 0 only (no pagination).

### 6.3 Taxonomy API

**Endpoint:** `GET https://api.ebay.com/commerce/taxonomy/v1/get_default_category_tree_id?marketplace_id=EBAY_DE`

**Purpose:** Resolve per-region category IDs for keyword-to-category mapping.

**Workflow:**
1. Query `getDefaultCategoryTreeId` for `EBAY_DE` and `EBAY_US`.
2. Cache category tree locally (refresh monthly).
3. Map keywords to leaf category IDs for filtered queries.

**DE-specific category examples:**
- `Sport > Camping & Outdoor > Outdoor-Schuhe > Wanderschuhe`
- `Sport > Radsport > Fahrradtaschen & Körbe`

### 6.4 Regional Headers & Marketplace Mapping

| Parameter | US (EBAY_US) | Germany (EBAY_DE) |
|-----------|-------------|-------------------|
| **Browse API header** | `X-EBAY-C-MARKETPLACE-ID: EBAY_US` | `X-EBAY-C-MARKETPLACE-ID: EBAY_DE` |
| **Finding API param** | `GLOBAL-ID=EBAY-US` | `GLOBAL-ID=EBAY-DE` |
| **Site ID** | `0` | `77` |
| **Currency** | USD | EUR |
| **Language header** | `Accept-Language: en-US` | `Accept-Language: de-DE` |
| **Buyer context** | `contextualLocation=country=US,zip=90210` | `contextualLocation=country=DE,zip=10115` |

### 6.5 Error Handling & Rate Limit Strategy

**Rate limit headers:**
- `X-RateLimit-Limit` — daily quota
- `X-RateLimit-Remaining` — calls left
- `X-RateLimit-Reset` — reset timestamp

**Handling strategy:**
| Scenario | Response |
|----------|----------|
| `429 Too Many Requests` | Exponential backoff: 1s, 2s, 4s, 8s, 16s. Max 5 retries. |
| `500` / `503` eBay error | Retry after 5s. If persistent, abort snapshot and alert operator. |
| Daily quota exhausted | Halt remaining calls. Resume next day at 06:00 UTC. Mark incomplete snapshot in DB. |
| Auth token expired | Refresh OAuth token (client credentials flow). Token lifetime: 2 hours. |

**Operational monitoring:**
- Track calls consumed per hour vs. budget.
- Alert if >80% of daily budget consumed before 12:00 UTC.
- Log all API errors with keyword, marketplace, and retry count.

---

## 7. Keyword Universe (v1 — 50 Terms)

### 7.1 Allocation Rules
- **50 keywords total** (council cap).
- Split: ~30 DE-focused, ~20 US-focused. Some overlap (Birkenstock, Patagonia).
- Model-level granularity where possible ("Birkenstock Arizona" not just "Birkenstock").
- Each keyword is paired with `condition:USED` and split into BIN + Auction tracks.

### 7.2 Germany (DE) — 28 Terms

| # | Keyword / Model | Category Context | Rationale |
|---|-----------------|-------------------|-----------|
| 1 | Birkenstock Arizona | Schuhe > Sandalen | Peak S/S; high liquidity |
| 2 | Birkenstock Boston | Schuhe > Clogs | DE prefers over Arizona for transitional |
| 3 | Birkenstock Gizeh | Schuhe > Sandalen | Thong style; S/S demand |
| 4 | Birkenstock Madrid | Schuhe > Sandalen | Single-strap; volume driver |
| 5 | Lowa Renegade GTX | Outdoor > Wanderschuhe | Highest resale velocity in outdoor |
| 6 | Meindl Bhutan | Outdoor > Wanderschuhe | Strong DE presence |
| 7 | Meindl Ortler | Outdoor > Wanderschuhe | Volume model |
| 8 | Ortlieb Back-Roller | Radsport > Taschen | Cyclist seasonality (May–Sep) |
| 9 | Ortlieb Velocity | Radsport > Taschen | Messenger bags |
| 10 | Jack Wolfskin 3in1 | Outdoor > Jacken | Massive domestic volume |
| 11 | Jack Wolfskin DNA | Outdoor > Jacken | Newer line; growing resale |
| 12 | Deuter Aircontact 65+10 | Outdoor > Rucksäcke | Backpacking season |
| 13 | Deuter Futura | Outdoor > Rucksäcke | Day hiking |
| 14 | Vaude Brenta | Outdoor > Rucksäcke | DE outdoor brand |
| 15 | Patagonia Retro-X Fleece | Outdoor > Fleece | Transitional season |
| 16 | Patagonia Better Sweater | Outdoor > Fleece | Year-round; lighter for S/S |
| 17 | Patagonia Nano Puff | Outdoor > Isoliert | Lightweight; S/S camping |
| 18 | Arc'teryx Beta LT | Outdoor > Hardshells | Premium shell; S/S rain |
| 19 | Arc'teryx Atom LT | Outdoor > Isoliert | Mid-layer; S/S evenings |
| 20 | Arc'teryx Zeta SL | Outdoor > Hardshells | Lighter S/S shell |
| 21 | Vintage Levi's 501 | Vintage > Jeans | Festival season (May–Jun) |
| 22 | Levi's 501 Made in USA | Vintage > Jeans | Premium selvedge segment |
| 23 | Miu Miu Ballerinas | Damen > Schuhe | "Balletcore" S/S trend |
| 24 | Repetto Ballerinas | Damen > Schuhe | French classic; DE demand |
| 25 | Chanel Ballerinas | Damen > Schuhe | Luxury resale |
| 26 | Birkenstock EVA | Schuhe > Sandalen | Lower price, fast-moving |
| 27 | Lowa Camino GTX | Outdoor > Wanderschuhe | Higher-end Lowa model |
| 28 | Meindl Borneo | Outdoor > Wanderschuhe | Niche but loyal following |

### 7.3 United States (US) — 22 Terms

| # | Keyword / Model | Category Context | Rationale |
|---|-----------------|-------------------|-----------|
| 29 | Birkenstock Arizona | Shoes > Sandals | US peak; beach/festival |
| 30 | Birkenstock Boston | Shoes > Clogs | Growing trend |
| 31 | Birkenstock Gizeh | Shoes > Sandals | Thong; volume |
| 32 | Vintage Levi's 501 80s | Vintage > Jeans | "Big E" era premium |
| 33 | Vintage Levi's 501 90s | Vintage > Jeans | Orange tab; accessible volume |
| 34 | Levi's 501 Red Line | Vintage > Jeans | Selvedge premium |
| 35 | Patagonia Retro-X Fleece | Outdoor > Fleece | US staple |
| 36 | Patagonia Better Sweater | Outdoor > Fleece | Year-round |
| 37 | Patagonia Nano Puff | Outdoor > Insulated | Lightweight S/S |
| 38 | Patagonia Houdini | Outdoor > Windbreakers | S/S layer |
| 39 | Arc'teryx Beta LT | Outdoor > Shells | Premium; S/S rain |
| 40 | Arc'teryx Atom LT | Outdoor > Insulated | Mid-layer |
| 41 | Arc'teryx Alpha SV | Outdoor > Shells | Hardcore; year-round |
| 42 | Arc'teryx Zeta SL | Outdoor > Shells | Lighter S/S |
| 43 | Lowa Renegade GTX | Outdoor > Hiking Boots | Niche US following |
| 44 | Meindl Bhutan | Outdoor > Hiking Boots | Niche |
| 45 | Tory Burch Ballet Flats | Women > Shoes | US "balletcore" |
| 46 | Miu Miu Ballet Flats | Women > Shoes | Trending luxury |
| 47 | Birkenstock EVA | Shoes > Sandals | Fast-moving; low price |
| 48 | Patagonia Synchilla | Outdoor > Fleece | Classic; S/S evenings |
| 49 | Arc'teryx Gamma MX | Outdoor > Softshells | All-season |
| 50 | Vintage Levi's 501 Shrink-to-Fit | Vintage > Jeans | Raw denim niche |

---

## 8. Known Blind Spots & Risks

### 8.1 Kleinanzeigen (No API)

**Status:** Explicitly acknowledged.

- Kleinanzeigen.de is the dominant German C2C classifieds platform for used clothing, shoes, and outdoor gear.
- Zero fees for private sellers means DE sellers often default to Kleinanzeigen over eBay.de for low-margin items.
- **Impact:** eBay.de captures a **filtered subset** of the German market: higher-value items, commercial sellers, and ship-able goods. The index does not represent the full DE used-goods landscape.
- **Product communication:** If marketed to DE resellers, explicitly state: *"Covers eBay.de only. Kleinanzeigen data not included due to lack of official API."*

### 8.2 Finding API Sunset Risk

**Status:** HIGH probability of deprecation within 12–24 months.

- Finding API is legacy XML/SOAP. eBay has pushed developers to Buy APIs since 2018.
- There is **no equivalent** `findCompletedItems` in the Buy API suite.
- Marketplace Insights API was the intended replacement but is **restricted and likely dead** for new users.
- **Hedging strategy (Council Condition #1):**
  - **Phase 1 (0–30 days):** Build on Finding API. Accept as temporary foundation.
  - **Phase 2 (30–90 days):** Parallel prototype using third-party scraping (Apify, ScrapeChain) for sold comps.
  - **Budget:** $50–100/month for scraping infrastructure.
  - **Criteria for switch:** If Finding API shows >5% active-listing contamination in validation, or eBay announces deprecation timeline.
  - **Fallback:** If both Finding API and scraping fail, the product cannot compute sold velocity. The pipeline shuts down for that data dimension.

### 8.3 Browse API `total` Unreliability

- eBay warns `total` is "just an indicator."
- Error propagates directly into the Sellability Index denominator.
- **Mitigation:** Manual validation protocol (§4.7) + failover to Finding API `totalEntries`.
- **Acceptable risk:** If divergence is quantified and bounded (<30%), the index remains directionally useful.

### 8.4 Cross-Border Arbitrage Signal Noise

- eBay's Global Shipping Program makes US→DE and DE→US transactions frictionless.
- A listing with `itemLocationCountry:DE` may sell to a US buyer (and vice versa).
- **Impact:** `SoldUnits` for a marketplace may reflect foreign demand, not domestic.
- **Mitigation:** None via API. eBay does not expose buyer country in public APIs.
- **Product note:** Scores measure *listing liquidity on that marketplace*, not *domestic demand*. This is a semantic distinction users must understand.

### 8.5 No Real-Time Data — Snapshot Lag

- Pipeline runs once daily at 06:00 UTC.
- Finding API `endTime` lags actual sale date by 0–7 days (auction bias).
- **Impact:** The index reflects yesterday's market, not right now.
- **Mitigation:** Accept as structural limitation. Position as "daily market pulse," not real-time ticker.

### 8.6 Summary Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Finding API sunset | High | Existential | 90-day scraping hedge (§8.2) |
| `total` divergence | Medium | High | Validation + failover (§4.7) |
| Kleinanzeigen blind spot | Certain | Medium | Explicit product disclaimer |
| Cross-border noise | Medium | Low | Semantic framing in product |
| Snapshot lag | Certain | Low | Position as daily pulse, not real-time |
| Multi-variation inflation | Certain | Medium | Accept as upper-bound; confidence tag |

---

## 9. Implementation Phases

### Phase 1: Core Pipeline (Weeks 1–4)

**Goal:** Daily snapshots, index calculation, basic tabular reporting.

| Week | Deliverable |
|------|-------------|
| 1 | API credential setup (sandbox + production), OAuth flow, Taxonomy API category mapping |
| 2 | Browse API integration: active counts for all 50 keywords × 2 markets × 2 buying options |
| 3 | Finding API integration: sold counts (30-day window) for same universe; deduplication logic |
| 4 | Index calculation engine, confidence tagging, SQLite schema, daily cron scheduling, CSV/JSON report output |

**Success criteria:**
- 7 consecutive days of clean snapshot runs.
- All 50 keywords produce an index score.
- Zero keywords with "no data" errors.

### Phase 2: Heatmap Visualization + Trend Alerts (Weeks 5–8)

**Goal:** Human-readable output, automated alerting.

| Week | Deliverable |
|------|-------------|
| 5 | ASCII/text heatmap generator (console output) |
| 6 | Trend alert engine: flag keywords where ΔDemand crosses ±15% WoW |
| 7 | HTML dashboard (static) rendering heatmap + historical charts |
| 8 | Alert routing: email/Telegram notifications for Hot/Warm score transitions |

**Success criteria:**
- Heatmap renders within 5 seconds of snapshot completion.
- Alert system fires within 24 hours of threshold breach.
- Historical chart shows 30-day trend for any keyword.

### Phase 3: Optimization (Weeks 9–12)

**Goal:** Scale signal quality, reduce noise, future-proof architecture.

| Week | Deliverable |
|------|-------------|
| 9 | Keyword expansion analysis: evaluate next 50 candidates based on Phase 1–2 signal quality |
| 10 | ML-based confidence scoring: train simple regression on validation data to predict `total` divergence |
| 11 | Scraping prototype (Apify/ScrapeChain) as Finding API hedge |
| 12 | Migration decision: stick with Finding API or cut over to scraping based on contamination metrics |

**Success criteria:**
- Confidence tag accuracy improves (validated against manual samples).
- Scraping prototype produces comparable sold counts to Finding API within ±10%.
- Architecture supports 200+ keywords without rate-limit exhaustion.

---

## Appendix A: Council Conditions — Traceability Matrix

| # | Council Condition | Section Addressed |
|---|-------------------|-------------------|
| 1 | Deprecate Finding API within 90 days; build scraping hedge | §8.2, §9 Phase 3 Week 11 |
| 2 | Cap keywords to 50 | §7, §3.4 |
| 3 | Separate indices by marketplace and buying option | §2.2A, §2.2B, §5 |
| 4 | Add confidence tags | §2.5, §2.2C |
| 5 | Validate Browse API `total` against manual sample | §4.7 |
| 6 | Acknowledge Kleinanzeigen blind spot | §8.1, §1 Scope |
| 7 | Design for `total` failure (failover to `totalEntries`) | §4.8 |

---

*Document compiled by Architect subagent. All council conditions addressed. No code. No profit projections.*
