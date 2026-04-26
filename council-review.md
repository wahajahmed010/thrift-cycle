# Thrift-Cycle Predictor — Council Review

> Council convened: 2026-04-23 | Members: Analyst, Skeptic, Regional Strategist

---

## 1. Analyst — Data & Logic Review

### Sellability Index Formula
- **Formula:** `(SoldUnits_30d / ActiveListings) × ΔDemand`
- **Verdict: Mathematically sound, but operationally fragile.**
  - The ratio `SoldUnits / ActiveListings` approximates a sell-through rate. This is a valid proxy for liquidity.
  - `ΔDemand` as a WoW multiplier introduces compounding amplification. A 20% WoW spike turns a 0.10 sell-through into 0.12. This is directionally useful but **not a calibrated elasticity** — it's a heuristic, not a causal model.
  - **What's missing:**
    - No normalization for listing age. A 30-day-old listing still counts as "active" but has already failed to sell. This deflates the sell-through artificially.
    - No price decay curve. An item that sold at 50% of market price is not the same signal as one that sold at full price.
    - No confidence interval or sample size weighting. A keyword with 3 sold / 30 active gets the same index treatment as 300 / 3,000.

### 6 Noise Sources & Mitigations
- The report identifies 6 sources correctly: multi-variation, auction/BIN/BO variance, condition spread, seasonal lag, international/CBT contamination, relisted inventory.
- **Adequacy: Partial.** Mitigations are reasonable on paper but several are unenforceable via API:
  - "Track `itemOriginDate` vs `itemCreationDate`" — Finding API does not expose `itemOriginDate`. This is aspirational, not implementable.
  - "Filter by specific aspect values" — Aspect filtering requires knowing valid aspect names per category per marketplace, which must be fetched via Taxonomy API and maintained dynamically. Significant engineering overhead.
  - Condition ID sub-filtering (`4000` vs `5000`) is valid but reduces sample sizes dramatically, amplifying noise from small-N.

### WoW Trend Reliability from Daily Snapshots
- **Verdict: Feasible but noisy.**
  - Daily snapshots of Finding API `findCompletedItems` with rolling `lastSoldDate` windows can produce a time series.
  - However, `findCompletedItems` returns listings that ended in the date range, not items that *sold* in the date range. A 7-day auction that ended on day 7 but sold on day 3 will still appear in day 7's snapshot with `sellingStatus.currentPrice`. The API does not expose the actual transaction date, only the listing end date.
  - This introduces a **lag distortion**: a sold item is backdated to its listing end, not its sale date. For fixed-price items (which sell same-day or near-instant), this is minor. For auctions (especially 7-day), it's a 1–7 day smear.
  - **Mitigation:** Separate trends by `ListingType`. Track BIN-only for fast signals; treat auction data as lagged.

### 5K/Day Rate Limit for 150–200 Keywords
- **Verdict: Tight, but workable with discipline.**
  - 5,000 calls / 200 keywords = 25 calls per keyword per day.
  - A single keyword may need multiple calls to paginate through results (page size 100–200). If any keyword returns >2,000 results, it exhausts its budget in 10–20 calls.
  - **At 200 keywords, you cannot paginate deeply.** You must either:
    1. Accept approximate counts from page 1 (`totalEntries` / `total`), or
    2. Reduce keyword count to ~50–80 and paginate 2–3 pages each.
  - **Recommendation:** Cap tracked keywords at 100. Use `findItemsAdvanced` (not `findCompletedItems`) for active counts where possible, since active counts need less precision than sold comps.

---

## 2. Skeptic — Anti-Hype & Risk Review

### Weakest Link in the Architecture
- **The Finding API.** It is legacy XML (not REST), officially in maintenance mode, and known to return active auctions when asked for completed items. The entire Sellability Index is built on a deprecated endpoint that eBay has not invested in for years.
- If Finding API returns even 5% active listings in "completed" results, your `SoldUnits_30d` is systematically inflated. Without ground-truth validation, you cannot detect this drift.

### Completed Items Data Accuracy
- **Verdict: Not accurate enough for a scoring system without calibration.**
  - `SoldItemsOnly` filter exists but is poorly documented and inconsistently applied by eBay's backend. Community reports show mixed results.
  - `sellingStatus.currentPrice` reflects the *final price*, but for Best Offer listings, this is the accepted offer — which is actually the *real* transaction price. However, for auctions, it is the hammer price, which may not include shipping. API does not expose buyer-paid total.
  - **Missing:** Buyer location, shipping cost, returns accepted — all affect true net revenue for a reseller. The index treats "sold" as binary; it is not.

### eBay Deprecates Finding API
- **Verdict: High probability of forced migration within 12–24 months.**
  - eBay has been pushing developers to Buy APIs (REST/JSON) since 2018. Finding API is SOAP/XML and unsupported in new SDKs.
  - There is **NO** equivalent `findCompletedItems` in the Buy API suite. Marketplace Insights API was the intended replacement, but it is restricted and likely dead for new users.
  - **If Finding API is sunset before Marketplace Insights opens, the pipeline has no official data source for sold comps.** This is an existential dependency.

### Multi-Variation Listing Problem
- **Verdict: Underestimated in the report.**
  - A parent listing with 10 size/color variations is counted as ~10 in `total` (Browse API). A single size selling out does not mean the "product" is liquid; it means one SKU moved.
  - For footwear (Birkenstock, Lowa, Levi's), this is critical. A size 46 Lowa Renegade selling 5x does not mean size 42 will sell.
  - The report's mitigation — "filter by specific aspect values" — is correct but requires a combinatorial explosion of queries. At 10 sizes × 3 conditions × 2 buying options = 60 API calls per keyword. With 100 keywords, that's 6,000 calls for ONE snapshot. Not viable under 5K/day.
  - **Practical outcome:** The index will blend fast-moving SKUs with dead SKUs, producing a false sense of liquidity.

### Failure Mode: Browse API `total` Is Wildly Off
- eBay explicitly warns: *"total is just an indicator... strongly recommended that total not be used in pagination use cases."*
- If `total` is an estimate (not a count), then `ActiveListings` in the denominator is a guess. A 30% error in `total` propagates directly into the Sellability Index.
- **No mitigation exists.** You cannot verify `total` without iterating all pages, which is impossible at scale. The index is built on an unverified denominator.

---

## 3. Regional Strategist — DE vs US Market Review

### DE-Specific Dynamics
- **Kleinanzeigen is not out of scope — it's a blind spot.**
  - eBay Kleinanzeigen (now Kleinanzeigen.de) is the dominant C2C classifieds platform in Germany, especially for used clothing, shoes, and outdoor gear. It operates with **zero fees for private sellers**, so DE sellers often default to Kleinanzeigen over eBay.de for low-margin items.
  - This means eBay.de captures a **filtered subset** of DE used goods: higher-value items, commercial sellers, and items where shipping is practical. The report treats eBay.de as representative of the German market. It is not.
- **German consumer behavior:**
  - DE buyers are more price-sensitive and condition-obsessed than US buyers. "Sehr gut" (Very Good) in DE is closer to "Like New" in US expectations.
  - Returns culture is weaker in DE for private sellers; buyers scrutinize photos more before purchase. This slows velocity for listings with poor imagery, an effect not captured by API data.
- **VAT implications:**
  - DE business sellers (Gewerbe) must charge 19% VAT. Private sellers do not. This creates a ~16% price spread on identical items. The index does not distinguish seller type, so `sellingStatus.currentPrice` conflates tax-included and tax-exempt prices.
  - US has no federal VAT; state sales tax is not reflected in eBay API prices either. Cross-market price comparisons are apples-to-oranges.

### Seasonal Trends: DE vs US
- **They do NOT hold equally.**
  - DE hiking season starts later (mid-May in Alps) but peaks harder in July–August. US hiking season is broader (March–October) due to geographic diversity.
  - DE festival season (May–June: Maifest, Karneval der Kulturen) drives vintage fashion demand earlier than US festival season (Coachella in April, then summer).
  - **Birkenstock:** Peak demand in DE is June–August (indoor/outdoor transitional use). In US, it's April–July (beach/festival-driven). The report conflates these into a single "April–July" peak.
  - **Arc'teryx / Patagonia:** DE demand for technical outerwear is concentrated in September–November (Herbstwandern). US demand is more year-round but dips in deep summer. A single seasonal model fails both markets.

### Brand Selection
- **DE-heavy brands (Ortlieb, Meindl, Lowa):** Correctly identified as stronger on eBay.de. However, these are **niche** in the US. The index must weight by marketplace, not blend them.
- **US-heavy brands (Levi's, Arc'teryx):** Levi's 501 vintage market is dominated by US sellers. DE volume is low but prices are higher due to scarcity. The index should not treat low-DE-volume as "illiquid" — it may be "high-margin, low-frequency."
- **Birkenstock:** Neutral. Strong in both, but model preferences differ (Arizona > Boston in US; Boston > Arizona in DE for transitional seasons).
- **Missing DE brands:** Jack Wolfskin (massive in DE, invisible in US), Deuter (backpacks), Vaude (outdoor). These are volume drivers on eBay.de that the report ignores.

### Cross-Border Arbitrage
- **Significant and growing.**
  - eBay's Global Shipping Program (GSP) and newer international shipping services make US→DE and DE→US transactions frictionless for buyers.
  - A Levi's 501 "Big E" listed on eBay.com at $800 is accessible to a DE buyer paying €740 + shipping + import VAT (~€140). Total landed cost: ~€880. A DE seller listing the same item at €900 on eBay.de may lose to the US listing.
  - **Effect on index:** Cross-border sales inflate `SoldUnits` for the domestic marketplace where the listing resides, but the buyer may be foreign. This means `itemLocationCountry:DE` does not guarantee a DE buyer. Demand signals are geographically smeared.
  - **Mitigation:** None via API. eBay does not expose buyer country in public APIs.

---

## Council Verdict

### **CONDITIONAL GO**

The Thrift-Cycle Predictor is **directionally viable but structurally fragile**. The concept is sound; the execution depends on deprecated infrastructure and optimistic assumptions about data quality. We approve proceeding only if the following conditions are met:

1. **Deprecate Finding API dependency within 90 days.** Build a parallel prototype using third-party scraping (e.g., Apify) for sold comps as a hedge against Finding API sunset. Budget $50–100/mo for scraping infra. Treat Finding API as temporary, not permanent.

2. **Cap initial keyword universe to 50 core terms**, not 150–200. Validate signal quality on a small set before scaling. Focus on 10 brands × 5 keywords each. This respects rate limits and reduces noise.

3. **Separate indices by marketplace (DE vs US) and by buying option (BIN vs Auction).** Do not produce a single blended score. Auction sell-through and BIN sell-through are different products; blending them destroys signal.

4. **Add a "confidence tag" to every index score.** Flag scores derived from <30 sold units or <100 active listings as "low confidence." Do not present these as equal to high-volume scores.

5. **Validate Browse API `total` against a manual sample.** For 20 keywords, paginate through all results and compare actual count to `total`. Quantify the error rate before trusting it in production.

6. **Acknowledge Kleinanzeigen blind spot in the product.** If the tool is marketed to DE resellers, explicitly state that it covers eBay.de only, not the broader German used-goods market.

7. **Design for `total` failure.** If Browse API `total` diverges >30% from ground truth, fall back to `totalEntries` from Finding API `findItemsAdvanced` for active counts. Document this failover.

**If these conditions are not met, the Council revises its verdict to NO-GO.**
