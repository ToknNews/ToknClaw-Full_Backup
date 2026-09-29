# Tokn Market Watch: subscriber value and next product work

Status: September 29, 2026. Product hypotheses below are not validated demand or performance claims. Conditional position playbooks, follow-through and a read-only historical mark-outcome report are implemented. Price-defined entry/exit setups and a validated edge remain future work. Demand and sustained operation remain unverified.

## Key facts

- Current inputs: BTC, ETH and SOL mark prices, open interest and funding from Hyperliquid and OKX. The default requires fresh coverage from both venues.
- Current product: reproducible condition alerts, morning/evening briefs, a daily BTC sample, archive and delivery receipts. The updated cards identify conditional continuation scenarios, separate long/short/new-entry considerations, quantify funding carry and display the configured condition thresholds. Briefs open with asset-by-asset context.
- Not yet implemented: support/resistance or candle-based entry triggers, simulated trade-performance reports, subscriber-level preferences, checkout/access management, or a demonstrated trading edge.
- The operator has verified a Discord connection test, healthy collection cycles, delivered briefs/coverage cards and follow-through installation. A real original-alert/follow-up pair, sustained operation and paid demand still need verification.
- CoinGlass already publishes funding comparisons and offers price/open-interest alerts. That makes another feed of those measurements a weak basis for differentiation. This is a product judgment, not evidence that nobody would buy it.

## Analysis

### The buyer and the job

Initial customer hypothesis: a self-directed crypto trader who understands perpetuals but does not want to keep several data dashboards open. The job is to explain a material change, make the evidence easy to inspect, and tell the reader when to revisit the interpretation.

Working positioning: **Know what changed. Know what would change the read.**

The recurring value should come from selection, explanation and follow-through. Clear writing helps comprehension; retention must establish whether those benefits are worth paying for. Attractive cards alone do not establish an analytical advantage.

### What actionable means

The current update adds conditional position playbooks: separate guidance for existing longs, existing shorts and new entries, a directional scenario derived from price/OI agreement, and a quantified funding-cost comparison. Funding watches also notify changes in the separate directional scenario. See `POSITION_PLAYBOOKS.md`. It does not turn the alert threshold into a trade entry. A threshold crossing on a rolling 15-minute comparison is also not a stop-loss.

A future scenario card can define a directional hypothesis, a measurable confirmation condition, an invalidation condition and an expiry time. Numeric market levels require suitable historical candle data and a declared method. The existing mark snapshot is not support, resistance, a traded price or an executable fill.

Price plus rising open interest does not identify net new longs or shorts. Extreme funding does not establish a reversal. Cross-venue agreement is corroboration, not statistical independence or a probability of profit.

Paid derivatives guidance needs a focused legal review for the intended product and jurisdictions. NFA includes advice through publications in its CTA description and describes a conditional exemption for certain standardized advice. Non-personalized wording or a disclaimer alone is not a determination that this product qualifies. Avoid tailoring recommendations to customer holdings or automatically executing customer trades while that scope is unresolved.

## Recommendations

### 1. Alert follow-through: implemented, awaiting live pilot verification

Subscriber benefit: learn whether the condition behind an alert persisted, faded, expired, or became unobservable.

Implemented behavior (see `FOLLOW_THROUGH.md` for exact limits and rollout):

- Store a scenario record linked to the original archived event, rule version, configuration, venue cohort and source observations.
- Re-evaluate with fresh data at defined intervals. Default interval: five minutes; observation horizon: 60 minutes; at most four updates including closure; validate it in the pilot rather than presenting it as optimal.
- Separate the current rolling-window condition from changes since the original alert. For example, a rolling price/OI threshold can stop qualifying even while price remains above its alert-time mark.
- Keep `unavailable` separate from `condition faded`. Missing data must not invent a market outcome.
- Publish only meaningful state changes, with a per-scenario cap and expiry. Route updates through the existing audience-bound outbox and persist deduplication across restarts.
- Keep a state meaning the pattern persisted separate from any claim that a trade was confirmed. No win/loss label without a predefined trade model.

Offline replay and restart tests are implemented and pass. Remaining acceptance: deploy the update and inspect the full original-alert-to-follow-up experience and original-message receipts in the private Discord pilot.

### 2. Honest outcome reports: implemented for operator research

Subscriber benefit: inspect what happened after every qualifying alert, including unfavorable outcomes and missing observations.

Implemented: `outcomes` reads per-venue mark changes at predeclared 15-, 60- and 240-minute horizons from the existing archive. It groups issued alerts by rule/version, thresholds, venue/instrument cohort and directional context; includes measured/pending/missing counts; and lists unsupported evidence as exclusions. It uses the first valid reading at/after the horizon within 180 seconds, respecting source and receipt time cutoffs. It does not substitute a late outage-recovery price. It measures from the original event, not receipt/entry time; delivery-time performance is not modeled. This is an operator report, not automatically published customer statistics.

These are market movement observations, not subscriber P&L or an achievable win rate. Sampled maxima/minima are not intrabar extremes. A future simulated trading report needs frozen entry/exit rules, fees, funding, slippage and fill assumptions, plus out-of-sample evaluation. Existing ToknClaw paper results do not automatically validate this product.

Offline acceptance passes: every selected initial alert is included or explicitly excluded, every included venue/horizon is counted, source/fetch lookahead and late substitutions are rejected, and the report does not collect, publish or modify the archive. Actual production results require running it on the server.

### 3. Session context and level-based scenarios

Subscriber benefit: understand the move relative to its recent range and identify a specific condition worth waiting for.

Dependencies: verify an appropriate candle/volume feed and display rights; add completeness checks, minimum history and session boundaries. Start with clearly defined previous-session high/low and range measures. A reclaim or breakout condition needs an explicit close/retest definition, horizon and invalidation rule. Validate the methodology before distributing trading instructions or success claims.

Acceptance: scenarios use only data available at issuance; incomplete history suppresses derived levels; published prices identify venue and quote currency.

### 4. A fast catch-up brief

Subscriber benefit: answer what changed since the previous briefing and which assets currently meet the product's rules.

Current delivery includes an at-a-glance snapshot. A true catch-up needs historical comparison across the stated period and links to prior events. Summarize active conditions and changes, not a forced top pick. If nothing qualifies, say no condition qualifies; do not describe the market as safe or guarantee inactivity is optimal.

### 5. Funding-cost context and event risk

Implemented: cards show estimated long/short cash flow per 10,000 quote-unit notional on an 8-hour-equivalent basis at unchanged rates; evidence also records the actual-interval estimate. Funding-gap cards identify the more favorable rate for each side and require considering switching costs. This is a comparison tool, not a guaranteed carry return.

Later, reuse ToknNews ingestion for sourced, time-stamped context or upcoming scheduled events. Confirm reliability, latency and usage rights first. A nearby headline is not proof it caused a move. Defer this integration until the core subscription has paid demand.

## Packaging and validation

- Keep one paid pilot tier initially. The existing free BTC morning sample can demonstrate writing quality. Paid coverage currently adds ETH/SOL and condition alerts; include lifecycle updates only after live verification; performance reports remain planned.
- Test the existing price hypothesis ($29 introductory month with clearly disclosed $49 renewal) with 5–10 paying pilot customers. This is an experiment, not a price validated by the research above.
- Ask which specific message changed a research decision, what was unclear, what felt repetitive and why they would renew. Measure paid conversion, refunds, cancellations, renewal and support time; free signups do not establish willingness to pay.
- Judge contribution after hosting, membership/payment fees, licensed data, refunds and support. Low server cost alone does not establish a profitable business. Do not add premium data subscriptions until a feature's benefit justifies them.
- Continue operations hardening and a private reliability pilot alongside product work. Delivery reliability and understandable content are both necessary.

The copy revision uses deterministic templates and the existing data. It adds no paid model calls or data vendor subscription. Lifecycle tracking uses the current Python/SQLite stack. Descriptive outcome evaluation is now implemented; trade simulation and out-of-sample edge validation remain planned; ongoing operational cost and subscriber value still need to be measured.

## Sources checked September 29, 2026

- CoinGlass alerts: https://www.coinglass.com/alert
- CoinGlass funding comparisons: https://www.coinglass.com/FundingRate
- NFA CTA overview: https://www.nfa.futures.org/members/cta/index.html
- NFA interpretive notice 9055: https://www.nfa.futures.org/rulebooksql/rules.aspx?RuleiD=9055&Section=9

Sources establish competitor feature availability and the need to review the advice model. They do not establish demand, legal eligibility or trading performance for Tokn Market Watch.
