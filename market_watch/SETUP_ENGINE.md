# Tokn Setup Engine v1

Prospective five-minute breakout/retest scenarios for BTC, ETH and SOL. Each setup freezes its venue, range, trigger, invalidation, reference targets and rule configuration at issuance. This is a research and notification product. It neither submits orders nor measures realized trading returns.

The release adds no Python dependencies, paid data subscription, model calls or exchange credentials. Existing price/OI alerts and their watches remain independent. No legacy ToknClaw trading engine or mutable paper-trade state is imported.

## What subscribers receive

| Card | Meaning |
| --- | --- |
| SETUP FORMING | Price is approaching the edge of a qualifying range. Preparation only. |
| BREAKOUT CONFIRMED | A closed candle broke the frozen trigger with sufficient volume. A later retest is still required. |
| RETEST CONFIRMED | A subsequent candle retested and closed through the trigger; the current indicative quote also passed the entry-band and liquidity checks. This is not an execution receipt. |
| FIRST / SECOND LEVEL REACHED | A later candle touched a reference target. The second target ends tracking. |
| THESIS INVALIDATED | A subsequent candle touched the fixed invalidation. Distinguish failure before a trigger from failure after one in archived evidence. |
| ENTRY CHECKS PAUSED / CHECKS RESTORED | Required price or liquidity checks are unavailable, or recovered. No missing reading becomes confirmation. |
| OUTCOME UNCLEAR | Both the invalidation and next target were touched in one candle. Their intrabar order is unknown. |
| TRACKING INCOMPLETE | At least one decision candle was missed. No catch-up entry or favorable outcome is inferred. |
| WATCH ENDED | Entry expiry, monitoring horizon, or update budget was reached. A tracking deadline is not a forced trade exit. |

Every card includes direction-aware guidance for waiting, long and short readers; exact Hyperliquid price references; volume, funding and OI context where available; source coverage; and the original setup reference. Discord uses the existing Tokn artwork and blue palette. Telegram receives matching plain text. Templates are deterministic.

## Free sources and boundaries

| Source | Data | Use |
| --- | --- | --- |
| Hyperliquid `candleSnapshot` | Closed 5m OHLC and base-asset volume | Sole source of setup price levels and subsequent price-path checks |
| Hyperliquid `l2Book` | Source-timestamped bids and asks | Spread, current indicative entry quote and visible dollar depth within 10 bps of midpoint |
| OKX `/api/v5/market/candles` | Confirmed 5m perpetual candles | Separate 15m price comparison; swap base volume uses `volCcy`, not contract-count `vol` |
| Coinbase Exchange `/products/{asset}-USD/ticker` | Last spot trade, best quotes and 24h base volume | Separate USD spot reference; never substitutes for perpetual price evidence |
| Existing Market Watch collectors | Per-venue OI, funding and interval metadata | Context from fresh observations and valid stored OI baselines |

Primary levels remain on Hyperliquid even when another source is unavailable. USD and USDT quotes are not merged. Funding and OI context does not independently confirm a price direction; rising OI is not proof of net new longs. Book depth is a lower bound from the returned levels, not a full-depth liquidity guarantee. Spot reference is a different market and carries its last-trade timestamp in evidence.

The collector requests at most 64 history bars by default, once for each new closed five-minute bucket after a 15-second completion grace. With three assets and both optional sources enabled, a healthy batch adds 12 requests every five minutes. Failed primary batches retry no faster than once per minute; source-level HTTP 429 backoff survives restarts. All extra HTTP work uses a pool of at most three workers. Existing observation requests continue separately.

The October 4, 2026 workspace probe returned valid Hyperliquid candles and books. OKX and Coinbase returned HTML instead of JSON in this environment and were rejected. Their parsers are tested against documented schemas; availability from the deployed server must be checked. No HTML response, region change or alternate market is silently treated as data. Optional source failure appears in `optional_issues` and the card's unavailable context; it does not prevent a valid primary setup.

Official references checked October 4, 2026:

- https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint
- https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits
- https://app.okx.com/docs-v5/en/#rest-api-market-data-get-candlesticks
- https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-ticker
- https://docs.cdp.coinbase.com/exchange/rest-api/rate-limits

## Exact v1 rules

Rules are deliberately narrow and unvalidated as a trading edge. Changing the fixed arithmetic requires a new version, prospective evaluation and fixtures. Configuration thresholds are frozen per setup.

1. Require contiguous closed history covering every indicator window. The newest candle must match the requested bucket and be at most 150 seconds past close when evaluated. No missing lookback is filled with a recent sample.
2. Build the range from the preceding 12 candles, excluding the formation candle. ATR is the arithmetic mean of 14 true ranges from preceding candles; volume baseline is the mean of 20 preceding base-volume candles. These are not Wilder ATR or an EMA.
3. Range width must be between 2 and 6 ATR. The formation close is inside the range, within 20% of its chosen edge, above the previous 20-close mean for a long or below it for a short. The current book midpoint must still be near that edge, inside the range and on the valid side of invalidation.
4. Let direction `d` be +1 for long or -1 for short; let `L` be the selected range edge. Trigger = `L + d*0.10*ATR`; invalidation = `L - d*0.75*ATR`; retest zone = `L ± 0.20*ATR`. Planned risk `R` is the distance from trigger to invalidation. Reference targets = trigger + `d*1.5R` and trigger + `d*2.5R`. None move after issuance.
5. A subsequent candle must close through the trigger with at least 1.20 times the frozen volume baseline to arm the setup. At least one later candle must overlap the retest zone, close through the trigger in the intended candle direction, and remain inside the entry band. The entry band extends from trigger to trigger + `d*0.60*ATR`.
6. Both arming and triggering require a book no more than 60 seconds old, spread at most 8 bps and at least $10,000 of visible depth on each side within 10 bps. At a trigger, the current ask for a long or bid for a short must also be inside the entry band. A quote is not a fill; remaining target-2 reward/risk is shown before costs.
7. Touching invalidation ends the setup. Reaching the first target before a valid trigger ends it as an extended move; do not chase. After triggering, later closed candles evaluate target/invalidation touches. A candle crossing both the invalidation and next target is ambiguous, never a favorable ordering assumption. A boundary touch in the first candle overlapping card issuance also has unknown timing relative to that notification and is marked ambiguous. Target one remains active; target two completes tracking.
8. Untriggered setups expire after 60 minutes. Triggered setups have a 24-hour monitoring horizon; this is not a max-hold exit instruction. Gaps of more than one decision candle close tracking as incomplete. Intrabar paths, execution latency, fees, slippage and realized funding are not modeled.

One active setup per asset, at most three new setups per hour across the universe, a 60-minute cooldown after closure and a maximum of 12 ordinary updates bound noise. A final closing update may follow the update cap. These limits are independent of existing market-alert limits.

## Archive and delivery

Schema 3 adds `setup_candles`, `setup_samples`, `setups`, and `setup_events`. It does not delete or rewrite existing observations, events or receipts. Closed candles preserve first receipt; a later changed OHLC/volume row is flagged and withheld from fresh decisions, not silently substituted. A revision can suppress a source until the conflicting candle leaves the fetched history window. Source timestamps and first-receipt timestamps remain distinct; a historical candle fetched today was not available to this system yesterday.

Setup state, candle inserts, event evidence, queue changes, and successful poll completion commit together. After a rolled-back cycle the collector can retry. The existing process lock prevents overlapping workers.

Initial cards can target paid routes only. An update requires a confirmed receipt for the original card at that exact route fingerprint. A new route or a previously unsent original does not inherit updates. New state expires older pending cards, including queued initial cards, for that setup. Unknown sends remain quarantined. A destination throttled past the freshness deadline can miss a card; there is no exactly-once or complete-delivery claim.

The shipped configuration enables **shadow collection** (`setup_enabled: true`, `setup_publish: false`). All setup states and cards are archived, but setup cards are not enqueued. Existing alerts keep their existing publishing settings. Switching to live affects newly formed setups; existing shadow setups never become retroactive alerts. The normal `--send` and environment delivery gates still apply in live mode.

`setups` is an operator-only, read-only view of recent setup records, source issues and screen reasons. `screen` distinguishes a normal absence of qualifying ranges, cooldowns and liquidity exclusions from missing data. It does not contain a win rate. The existing `outcomes` command still evaluates original market alerts only; it is not a setup backtester.

## Upgrade on Ubuntu 22.04

Each command below is separate. Stop on any failure. No SSH deployment is performed by the development agent.

```bash
# Enter the deployed checkout.
cd /opt/tokn-market-watch
```

```bash
# Pause collection so code and schema cannot change during a running cycle.
sudo systemctl stop tokn-market-watch.timer tokn-market-watch.service
```

```bash
# Create a consistent pre-upgrade backup; this fails if the destination exists.
sudo python3 -m market_watch --database /var/lib/tokn-market-watch/state.sqlite3 backup /var/lib/tokn-market-watch/pre-setup-v1.sqlite3
```

```bash
# Check for local configuration edits before pulling. Do not discard them.
git status --short
```

```bash
# Fast-forward the reviewed feature branch. Stop if local changes cause a conflict.
git pull --ff-only origin feature/tokn-market-watch
```

```bash
# Run offline verification; no network data or messages are sent by these tests.
python3 -m unittest discover -s market_watch/tests -v
```

```bash
# Explicitly enable shadow collection and preserve a dated copy of the complete prior config.
sudo python3 -m market_watch.setup_config --config config/market_watch.json --mode shadow
```

```bash
# Preview a fictional confirmation card with no network access or publishing.
python3 -m market_watch.setup_preview --kind setup_triggered
```

```bash
# Start one service cycle using the existing protected environment and database path.
sudo systemctl start tokn-market-watch.service
```

```bash
# Inspect setup source coverage and any recorded candidates.
sudo python3 -m market_watch --config config/market_watch.json --database /var/lib/tokn-market-watch/state.sqlite3 setups --limit 10
```

```bash
# Resume the recurring timer after the upgrade succeeds.
sudo systemctl start tokn-market-watch.timer
```

```bash
# Check collector cadence, primary setup data and unresolved deliveries.
sudo python3 -m market_watch --config config/market_watch.json --database /var/lib/tokn-market-watch/state.sqlite3 check
```

An initial `closed_candle_missing_or_late` is possible if installation occurs late in a five-minute bucket. Check after the next closed bucket. Zero active setups is normal when no range qualifies. Optional source failures are recorded separately; a primary failure or a setup check more than ten minutes old fails `check` when setup collection is enabled.

### Publish newly formed setups after inspecting shadow coverage

```bash
# Enter the deployed checkout.
cd /opt/tokn-market-watch
```

```bash
# Pause the worker before an explicit publishing configuration change.
sudo systemctl stop tokn-market-watch.timer tokn-market-watch.service
```

```bash
# Enable paid setup delivery for new setups and save a dated prior-config backup.
sudo python3 -m market_watch.setup_config --config config/market_watch.json --mode live
```

```bash
# Resume the existing schedule. Existing send gates and paid destinations still apply.
sudo systemctl start tokn-market-watch.timer
```

Use the same paused-worker procedure with `--mode shadow` to stop setup publishing while retaining collection, or `--mode off` to stop setup ingestion and close active watches. Pending setup messages are withdrawn on the next cycle. These commands replace the complete validated configuration while preserving unrelated settings, and retain the prior bytes in a dated file. They do not modify the environment or webhook.

Do not run an older schema-2-only release against the migrated database. Prefer a forward code correction or disable the new behavior. Restoring a pre-upgrade database requires a deliberate reconciliation of later observations and delivery receipts; no destructive downgrade command is provided.

## Preview and next validation milestone

`SETUP_PREVIEW.html` is a self-contained gallery of twelve fictional cards, including a short scenario and alternate failure paths. It makes no network requests and contains no posting controls. Actual Discord fonts and wrapping vary by client. Browser screenshot verification was unavailable in this workspace because the browser binary download returned an invalid archive; native Discord rendering still needs a visual check.

The next product gate is a prospective shadow/live pilot: inspect coverage and alert frequency, preserve every setup (including failures and missing paths), and evaluate whether the trigger/invalidation definitions help subscribers. Validate a separate timestamp-correct execution simulation with costs before publishing trading performance. A successful unit suite establishes rule behavior, not a profitable edge.
