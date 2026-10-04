# Position playbooks and historical alert outcomes

> Setup Engine v1 is now implemented separately. For the current schema-3 upgrade procedure, shadow/live modes and price-defined setup cards, use [SETUP_ENGINE.md](SETUP_ENGINE.md). The older rollout instructions below describe their original release.

This release adds conditional positioning guidance and an operator-only outcome report. It does not add a tested entry/stop/target model or establish positive expectancy. Branding and the database schema remain unchanged.

## What subscribers receive now

- **The read:** bullish continuation, bearish continuation, or unconfirmed direction, derived from actual price and coin-unit OI comparisons. Funding sign alone cannot assign a direction. All covered venues need valid, agreeing price/OI baselines before a directional scenario is displayed.
- **Position playbook:** separate considerations for existing longs, existing shorts and new entries. A fresh expansion supports considering continuation; a faded expansion removes that basis for new adds. It is not itself a reversal or an automatic exit of every existing position.
- **Funding gap:** identify the lower normalized rate for more favorable long carry and the higher rate for more favorable short carry. This ordering works for positive, negative and mixed-sign rates. Compare gross basis-point differences with round-trip fees, spread, slippage and basis before switching. It is not a recommendation to open an unhedged position just to receive funding, nor a proven net arbitrage.
- **Funding budget:** long debit/credit and opposite short cash flow per 10,000 quote-unit notional, normalized to 8 hours at unchanged rates. USD and USDT are labeled separately and no stablecoin conversion is assumed. Actual settlement calculations, intervals and changing rates determine actual payments. The archived playbook also records each venue's actual-interval estimate.
- **What changes the read:** actual thresholds for the original condition and, on directional funding cards, the separate price/OI scenario. These are rule conditions, not price-level stop orders.
- **Position updates:** persistence, fade, missing data and expiry have different implications. Funding watches now notify a change in directional context even when the original funding rule holds. These consume the same capped update budget, keep receipt gating, and preserve pending-message supersession/restart behavior.

No customer holdings, account credentials, leverage choices or automated orders are involved. Existing long/short guidance is standardized. Scenario labels are hypotheses, not measured probabilities. The product can legitimately say a condition favors investigating continuation; it cannot yet say a setup has a proven win rate or should be entered at a specified level.

## Learn from retained data

The `outcomes` command reads the existing archive without collecting, publishing or changing it. No new database tables are needed. It can evaluate compatible past Market Watch alerts from before this release as well as new alerts.

Method `alert-mark-outcomes-v1`:

1. Select every archived paid **initial alert** in the requested time window. This is the issued-alert cohort, subject to original cooldowns/rate limits; it is not every market minute that met a condition. Include alerts with no delivery receipt as research observations; delivery-time performance is not modeled.
2. Group by asset, initial rule/version, original thresholds, venue/instrument cohort, comparison venues and directional price/OI context. Do not pool bullish and bearish funding scenarios together or mix venue quotes.
3. Measure each original venue's raw mark-price change at **15, 60 and 240 minutes** from event creation. Reference the original mark, including its actual source timestamp; it is not an executable entry fill.
4. Use the earliest valid source reading at/after each target and at most **180 seconds late**. Both source and receipt times must have been available by the report's as-of time; reject observations received after the allowed horizon window. Never carry an old price forward or use a much later outage-recovery quote.
5. Count every venue/horizon as measured, pending or missing. List unsupported/malformed alert evidence separately as exclusions. No favorable-outcome selection.
6. Report median/min/max endpoint mark changes, positive/negative/flat counts and denominators. `--details` includes each event ID, timing and selected sample. The min/max values are across endpoint outcomes, not intratrade maximum favorable/adverse excursions.

These are descriptive market outcomes, **not realized P&L, win rates, independent samples or calibrated forecast probabilities**. No execution fees, realized funding, spread or slippage are deducted. Overlapping alerts can share most of the same subsequent move. No minimum number alone proves an edge. Compare against appropriate base rates and untouched future/out-of-sample periods before publishing predictive claims.

The server already retains the necessary Market Watch snapshots, subject to its actual collection coverage. Historical OI and funding cannot be reconstructed from candles alone. Reusing an older ToknClaw archive requires verifying real price fields, timestamps, cadence, versions and missingness. One legacy module, `signal_engine/pipeline/backtesting_engine.py`, uses `clusters.total_value_usd` as a placeholder price proxy; those outputs cannot substantiate tradable price returns. The new report does not import that module or alter the trading stack.

## Run on your server

For an installation already at schema 2, use the pause/pull/test/resume commands in `MESSAGE_STYLE.md`. Earlier installations must first follow the backup/migration instructions in `FOLLOW_THROUGH.md`. Existing posts and queued events retain their archived presentation. New card behavior starts with newly generated events. The outcome report is local/operator-only; it is not automatically posted to Discord.

```bash
# Enter the deployed project.
cd /opt/tokn-market-watch
```

```bash
# Analyze the last 30 days of archived alerts without sending messages.
sudo python3 -m market_watch --config config/market_watch.json --database /var/lib/tokn-market-watch/state.sqlite3 outcomes --days 30
```

```bash
# Inspect every included event, horizon and selected source reading.
sudo python3 -m market_watch --config config/market_watch.json --database /var/lib/tokn-market-watch/state.sqlite3 outcomes --days 30 --details
```

```bash
# Preview a fictional funding card without network calls.
python3 -m market_watch.message_preview --kind funding_divergence
```

## Next analytical release: price-defined setups

The priority is a small, testable setup engine with closed candles, volume and enough complete history to define actual structure. Start with one setup family: breakout/retest continuation. Add failed breakout/reclaim only after the first works end-to-end.

Each prospective setup must freeze at issuance:

- Setup stage: forming, armed, triggered, invalidated or expired. Forming/armed alerts provide the opportunity to prepare before the entry condition, rather than only report an expansion after it happened.
- Venue, quote currency, timeframe, pre-existing range, and exact closed-candle/retest definition. Levels use only data available at issuance; incomplete history suppresses the setup.
- Trigger/entry assumption, price invalidation, target method, expiry and conditions for canceling an untriggered setup. A changed thesis is not automatically a filled stop.
- Long/short/flat action and subsequent changes to that plan. No unrecorded shifting of stops or targets after observing the outcome.
- Simulated fill method, latency, fees, realized funding and slippage. Mark-to-mark changes are insufficient to claim strategy profitability. Same-bar stop/target ordering must be handled conservatively or marked ambiguous.
- Complete forward record including failures and unavailable data, comparison against baseline behavior, sample uncertainty and out-of-sample results. Historical similarity becomes a filter only after validation; it must not become a persuasive but untested confidence score.

The desired customer experience is: **Here is the scenario; here is the condition to act; here is the condition to abandon it; here is what happened afterward.** The release here implements positioning context, carry arithmetic and retrospective outcome measurement. Price-defined entries/exits, predictive similarity scores and their validation remain future development.

## Primary references checked September 29, 2026

- Funding mechanism and hourly payments: https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding
- Funding direction and fee mechanism: https://www.okx.com/en-sg/help/perps-funding-fee-mechanism
- Open interest as one input alongside price/trend analysis: https://www.cmegroup.com/education/courses/introduction-to-futures/open-interest

These explain market mechanics; they do not validate Tokn's scenario rules or trading performance.
