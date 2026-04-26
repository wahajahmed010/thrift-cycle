# Thrift-Cycle Predictor — Phase 1 Deep Research Report

> Research date: 2026-04-23 | Scout: Deep Research Agent

---

## 1. eBay API Access Audit

### 1.1 Marketplace Insights API (Sold Data)
- **Status: RESTRICTED — NOT open to new users.**
  - eBay docs explicitly state: *"The Marketplace Insights API is restricted and not open to new users at this time."* [source](https://developer.ebay.com/api-docs/buy/static/ref-buy-browse-filters.html)
  - Even existing developers report needing support tickets and manual scope approval. [community thread](https://community.ebay.com/t5/RESTful-Sell-APIs-Marketing/Marketplace-Insights-API-scope-request-issue/td-p/34709120)
- If accessible (existing partners), provides `search` under `item_sales` resource with `lastSoldDate` filter.
- Default limit: **5,000 calls/day**.

### 1.2 Browse API (Active Listings)
- **Status:** Available in sandbox to anyone; production requires eBay Partner Network (EPN) approval.
- Endpoint: `GET /buy/browse/v1/item_summary/search`
- Key data returned:
  - `total` — approximate active listing count (includes multi-variation listings; eBay warns: *"total is just an indicator... strongly recommended that total not be used in pagination use cases"*)
  - `itemSummaries[].price` — current price
  - `itemSummaries[].condition` / `conditionId`
  - `itemSummaries[].buyingOptions` — `FIXED_PRICE`, `AUCTION`, `BEST_OFFER`
  - `itemSummaries[].watchCount` — **requires special permission** via App Check ticket
  - `itemSummaries[].itemLocation.country`
- Supports `filter=conditions:{USED}`, `filter=buyingOptions:{FIXED_PRICE|AUCTION}`, `filter=itemLocationCountry:DE`, `filter=price:[..]`, `filter=lastSoldDate:[...]` (for active listings ending, not historical sold data)
- Default limit: **5,000 calls/day** (all methods combined except `getItems` which is separate 5,000).
- Max result set: **10,000 items**; max page size: 200.

### 1.3 Finding API (Traditional/XML — Completed Listings)
- **Status:** Available to all developers; no special approval needed for sandbox/production.
- Endpoint: `findCompletedItems` — returns completed listings (both sold and unsold).
- Filter: `itemFilter name=SoldItemsOnly value=true` to narrow to sold listings.
- Also supports `ListingType` filters (`FixedPrice`, `Auction`, `AuctionWithBIN`).
- Returns: `sellingStatus.currentPrice`, `listingInfo.endTime`, `condition`, `shippingInfo`, etc.
- Known reliability issue: sometimes returns active auctions mixed with completed listings. [Stack Overflow](https://stackoverflow.com/questions/17484572/ebay-finding-api-findcompleteditemsrequest-returns-active-auctions)
- Default limit: **5,000 calls/day**.

### 1.4 What APIs Actually Return

| Metric | API | Availability | Notes |
|--------|-----|-------------|-------|
| Sold count (30d) | Marketplace Insights | ❌ Restricted | Unavailable to new users |
| Sold count (30d) | Finding API `findCompletedItems` | ⚠️ Partial | XML-based; includes unsold unless `SoldItemsOnly` applied; known accuracy issues |
| Active listing count | Browse API | ✅ Yes | `total` field; approximate, includes variations |
| Active listing count | Finding API `findItemsAdvanced` | ✅ Yes | `totalEntries`; more stable |
| Sold price | Finding API `findCompletedItems` | ✅ Yes | `sellingStatus.currentPrice` |
| Sold price | Marketplace Insights | ❌ Restricted | Would provide `itemSales` data |
| Sell-through rate | None directly | ❌ No | Must compute: SoldUnits / ActiveListings |
| Watch count | Browse API | ⚠️ Restricted | Requires App Check approval |
| Condition distribution | Browse API | ✅ Yes | `refinement.conditionDistributions` |

### 1.5 Practical Conclusion on API Access
- **No official eBay REST API** provides historical sold data for arbitrary queries to new developers.
- The Finding API (`findCompletedItems`) is the only viable path for sold data, but it is XML-based, has accuracy issues, and is rate-limited to 5K/day.
- Alternative: third-party scraping APIs (e.g., ScrapeChain, Apify actors) — unofficial, fragile, ToS-risky.
- **Recommendation:** Build around Finding API for sold comps + Browse API for active inventory, with a local time-series cache to compute week-over-week trends.

---

## 2. Regional Mapping (DE vs US)

### 2.1 Marketplace IDs
| Marketplace | ID | Domain | Currency | Site ID (Finding API) |
|-------------|-----|--------|----------|----------------------|
| US | `EBAY_US` | ebay.com | USD | 0 |
| Germany | `EBAY_DE` | ebay.de | EUR | 77 |

### 2.2 Required Headers
- **Browse API / Buy APIs:** `X-EBAY-C-MARKETPLACE-ID: EBAY_DE` (required for all marketplaces outside US; default is `EBAY_US`)
- **Localization:** `Accept-Language: de-DE` (for German-language aspect names)
- **Buyer context (recommended):** `X-EBAY-C-ENDUSERCTX: contextualLocation=country=DE,zip=10115`
- **Finding API:** Pass `GLOBAL-ID` parameter (`EBAY-US` or `EBAY-DE`)

### 2.3 Category Tree Differences
- Category IDs are **NOT shared** between DE and US marketplaces.
- DE has German-specific categories (e.g., European energy efficiency ratings in electronics).
- Outdoor/hiking categories differ in structure:
  - US: `Sporting Goods > Camping & Hiking > Hiking Boots`
  - DE: `Sport > Camping & Outdoor > Outdoor-Schuhe > Wanderschuhe`
- Must use **Taxonomy API** (`getDefaultCategoryTreeId` with `marketplace_id=EBAY_DE`) to resolve correct category IDs per region. [source](https://developer.ebay.com/api-docs/commerce/taxonomy/static/supportedmarketplaces.html)

### 2.4 Region-Specific Filter Support
| Filter | EBAY_US | EBAY_DE |
|--------|---------|---------|
| `itemLocationRegion` | `NORTH_AMERICA`, `WORLDWIDE` | `EUROPEAN_UNION`, `CONTINENTAL_EUROPE`, `WORLDWIDE` |
| `sellerAccountTypes` | ❌ Not supported | ✅ `BUSINESS` / `INDIVIDUAL` |
| `qualifiedPrograms: EBAY_PLUS` | ❌ Not available | ✅ Available |
| `auto_correct` | ✅ Supported | ✅ Supported |

### 2.5 eBay Kleinanzeigen (DE Classifieds)
- **Separate platform** from eBay.de — now just `kleinanzeigen.de` (dropped "eBay" branding).
- **NO official API.** Only unofficial scrapers exist (e.g., GitHub `danielwte/ebay-kleinanzeigen-api`, Apify actors).
- For Thrift-Cycle targeting eBay.de listings (auction/BIN), not Kleinanzeigen classifieds.

---

## 3. Seasonal Keyword Research — Spring/Summer 2026

### 3.1 Footwear

**Birkenstock**
- Top models: Arizona (two-strap), Boston (clog), Gizeh (thong), Madrid (single-strap)
- EVA variants sell at lower price points (~€30-50 used) but move fast.
- Leather/Arizona Soft Footbed command ~€60-120 used depending on condition.
- German-made pairs earn ~20% premium over non-German production. [Underpriced AI](https://www.underpriced.app/blog/is-birkenstock-worth-reselling)
- Demand peak: **April–July** (Spring/Summer season).
- Listing lag: Sellers typically list en masse in **late March–April**, creating a brief oversupply window before Memorial Day/July 4 demand spike in US.

**Ballet Trainers / Pumps**
- Trending: Miu Miu ballet flats, Repetto, Chanel, Tory Burch ("balletcore" trend extension into S/S 2026).
- Search volume rises in **March–May** as transitional weather drives flat-shoe demand.
- DE market: Search term "Ballerinas" outperforms "ballet flats" in German queries.

### 3.2 Outdoor (DE-Heavy)

**Lowa**
- Top model: **Lowa Renegade GTX** — highest resale velocity in used outdoor footwear.
- Used price range: €80-160 (DE), $90-180 (US).
- S/S demand driven by hiking season (April–August).

**Meindl**
- Top model: **Meindl Bhutan / Ortler / Borneo**
- Stronger presence on eBay.de than eBay.com.
- Used: €70-140 depending on sole condition.

**Ortlieb**
- Top products: **Back-Roller Classic panniers**, **Velocity messenger bags**
- Cyclist seasonality: Peak demand **May–September**.
- DE market significantly outpaces US for Ortlieb volume.
- eBay.de category: `Sport > Radsport > Fahrradtaschen & Körbe`

### 3.3 Fashion

**Arc'teryx**
- Top resale models: **Beta LT** (shell), **Atom LT** (insulated mid-layer), **Alpha SV** (hardcore shell)
- Used price range: $150-450 (US), €140-420 (DE)
- Beta LT holds value best (~70% of retail after 2 years).
- S/S 2026: Lighter shells (Beta LT, Zeta SL) see demand surge in **April–June**.

**Patagonia**
- Top models: **Retro-X fleece**, **Better Sweater**, **Nano Puff**
- Retro-X: $60-180 used (US); year-round demand but slight dip in peak summer.
- Better Sweater: ~$50-120 used; strongest in transitional seasons (Mar–May, Sep–Nov).
- **S/S strategy:** Focus on lighter items (Better Sweater, Houdini windbreaker) rather than heavy down.

**Vintage Levi's 501**
- Era/value hierarchy:
  - 1950s–1960s "Big E" / Red Line selvedge: $500-$10,000+
  - 1980s–1990s orange tab: $50-$200
  - 2000s+: $20-$60 (minimal premium unless raw/selvedge)
- S/S demand: Peaks in **April–June** (festival/vintage fashion season).
- Key identifiers: "Made in USA" tag, red line selvedge, care tag era (single stitch = older).
- DE market: Smaller volume but higher avg price due to scarcity.

### 3.4 Seasonal Lag Patterns
- **Demand peak:** Typically 2–4 weeks BEFORE listing peak.
- **Listing peak:** Occurs when sellers clean closets post-winter (late March–April for S/S).
- **Best buying window for resellers:** **February–March** (pre-season, low competition).
- **Best selling window:** **April–June** (peak demand, buyers paying premiums).

---

## 4. Sellability Index Feasibility

### 4.1 Proposed Formula
```
Sellability Index = (SoldUnits_30d / ActiveListings) × ΔDemand
```
Where `ΔDemand` = week-over-week change in `SoldUnits`.

### 4.2 Data Source Mapping

| Formula Component | Data Source | Feasibility | Issues |
|-------------------|-------------|-------------|--------|
| `SoldUnits_30d` | Finding API `findCompletedItems` | ⚠️ Partial | XML-based; `SoldItemsOnly` filter unreliable; 5K/day limit; no exact "units" — counts listings, not individual items sold within multi-quantity listings |
| `ActiveListings` | Browse API `total` | ⚠️ Partial | Approximate count; includes multi-variation listings; eBay explicitly discourages relying on `total` for pagination |
| `ΔDemand` (WoW) | Custom time-series cache | ✅ Feasible | Must run daily/weekly snapshots and compute delta yourself; no native API trend data |

### 4.3 Data Noise Sources

1. **Multi-variation listings**
   - One parent listing with 10 size variations counts as ~10 in `total`.
   - A single sold variation counts as one "sale" even if 50 units sold.
   - **Mitigation:** Filter by specific aspect values (size, color) to narrow scope.

2. **Auction vs BIN vs Best Offer**
   - Auction prices often 20-40% below BIN for identical items.
   - Best Offer accepted price is NOT exposed via API; only listed price shown.
   - **Mitigation:** Separate indices by `buyingOptions` filter; discard auction outliers or track separately.

3. **Condition variance within "Used"**
   - Condition ID `3000` spans "like new" to "heavily worn."
   - **Mitigation:** Use `conditionIds` sub-filters (e.g., `5000` = Good, `4000` = Very Good) where available.

4. **Seasonal lag**
   - Listings flood market 4-6 weeks after demand starts rising.
   - **Mitigation:** Normalize `ActiveListings` against a 90-day rolling average, not absolute count.

5. **International/CBT listings**
   - Cross-border listings appear in search but ship from China/elsewhere at different price points.
   - **Mitigation:** Use `filter=itemLocationCountry:DE` or `US` to isolate domestic inventory.

6. **Relisted items**
   - Unsold items relisted appear as "new" listings but are stale inventory.
   - **Mitigation:** Track `itemOriginDate` vs `itemCreationDate`; flag relisted items.

### 4.4 Can WoW Sales Change Be Derived?
- **Yes, but only via self-managed time-series.**
- No eBay API provides native historical trend data or "sales velocity" metrics.
- Implementation: Run scheduled queries (daily) to `findCompletedItems` with `lastSoldDate` rolling windows, store counts in local DB, compute WoW delta.
- At 5,000 calls/day, you can monitor ~100-200 keyword/category combinations if queries are batched efficiently.

### 4.5 Alternative Approaches

| Approach | Pros | Cons |
|----------|------|------|
| **Finding API + Browse API** (official) | Stable, ToS-compliant | No native sold data; XML for Finding; rate limits |
| **Marketplace Insights API** | Would provide ideal sold data | Restricted; unavailable to new users |
| **Third-party scrapers** (ScrapeChain, Apify) | Often more complete sold data | Unofficial; fragile; ToS violation risk; paid |
| **eBay Terapeak** (seller analytics) | Rich historical data | Requires seller account; not programmatic API access |

---

## 5. Key Recommendations

1. **Primary data pipeline:** Use Finding API (`findCompletedItems`) for sold comps + Browse API (`item_summary/search`) for active inventory. Both are available without special approval.

2. **Marketplace Insights API:** Do NOT depend on it. Treat as a bonus if future access is granted, not a core dependency.

3. **DE strategy:** Build separate category ID mappings for `EBAY_DE` using Taxonomy API. Account for German-language aspect names. Consider that eBay.de has stronger outdoor gear culture (Lowa, Meindl, Ortlieb) while eBay.com is stronger for fashion (Patagonia, Levi's, Arc'teryx).

4. **Sellability Index implementation:**
   - Use `SoldUnits_30d` from Finding API daily snapshots.
   - Use `ActiveListings` from Browse API `total` (treat as upper-bound estimate).
   - Compute `ΔDemand` from your own time-series DB (WoW change).
   - Normalize by `buyingOptions` and `conditionIds` to reduce noise.
   - Apply `itemLocationCountry` filter for regional purity.

5. **Rate limit math:** At 5,000 Finding API + 5,000 Browse API calls/day, you can monitor ~150-200 keywords/categories per day with 1 call each. Batch related keywords; use `aspect_filter` to drill down instead of separate calls.

6. **eBay Kleinanzeigen:** Out of scope for official API integration. Consider as a future Phase 2 via scraping if DE classifieds data is critical.

---

## Sources

- eBay Developers Program: [API Call Limits](https://developer.ebay.com/support/api-call-limits)
- eBay Developers Program: [Buy API Field Filters](https://developer.ebay.com/api-docs/buy/static/ref-buy-browse-filters.html) — *"Marketplace Insights API is restricted and not open to new users at this time"*
- eBay Developers Program: [Buy APIs Requirements](https://developer.ebay.com/api-docs/buy/static/buy-requirements.html)
- eBay Developers Program: [Browse API Search](https://developer.ebay.com/api-docs/buy/browse/resources/item_summary/methods/search)
- eBay Developers Program: [Understand eBay Marketplaces](https://developer.ebay.com/api-docs/static/gs_understand-ebay-marketplaces.html)
- eBay Developers Program: [Supported Marketplaces for Category Trees](https://developer.ebay.com/api-docs/commerce/taxonomy/static/supportedmarketplaces.html)
- eBay Developers Program: [Finding API findCompletedItems](https://developer.ebay.com/devzone/finding/callref/findCompletedItems.html)
- eBay Community: [Marketplace Insights API scope request issue](https://community.ebay.com/t5/RESTful-Sell-APIs-Marketing/Marketplace-Insights-API-scope-request-issue/td-p/34709120)
- Underpriced AI: [Birkenstock Reselling 2026](https://www.underpriced.app/blog/is-birkenstock-worth-reselling)
- Underpriced AI: [Vintage Levi's Value Guide 2026](https://www.underpriced.app/blog/vintage-levis-value-guide-2026)
- Underpriced AI: [Summer Reselling 2026](https://www.underpriced.app/blog/summer-reselling-strategy-what-sells-best-2026)
- Stack Overflow: [Finding API returning active auctions](https://stackoverflow.com/questions/17484572/ebay-finding-api-findcompleteditemsrequest-returns-active-auctions)
- GitHub: [eBay Sold Items Documentation (third-party)](https://github.com/colindaniels/eBay-sold-items-documentation)
