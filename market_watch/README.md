# Tokn Market Watch

An isolated market-monitoring product with native Discord cards and plain-text Telegram messages for BTC, ETH and SOL. It runs alongside ToknClaw without importing or changing its trading runner, paper positions, strategy configuration, legacy snapshots, or ToknNews Studio.

**Pilot implementation, not a claim of trading profitability.** No orders, exchange-account credentials, personalized advice, or LLM-generated measurements. Python 3.10+ standard library only; Ubuntu 22.04 works without pip dependencies.

## Distribution decision

**Launch the paid pilot on Discord.** Use one private paid channel managed by a hosted membership provider such as LaunchPass, plus an optional separate public sample channel. An incoming webhook is sufficient for publishing. Billing, customer identity, subscription entitlements, refund handling and role removal remain the membership provider's responsibility; this package does not implement or claim to replace them.

Telegram publishing is also implemented for later use. It is a notification adapter, not a payment bot. Telegram requires Stars for digital goods/services sold inside its bots or mini apps. Do not add a third-party checkout flow inside the Telegram bot. Decide on a compliant subscription/access flow before offering paid Telegram access. The Discord pilot avoids making that a launch dependency.

References checked September 28, 2026:

- [Discord webhook API](https://docs.discord.com/developers/resources/webhook#execute-webhook)
- [Telegram sendMessage](https://core.telegram.org/bots/api#sendmessage)
- [Telegram digital goods and Stars](https://core.telegram.org/bots/payments-stars)
- [LaunchPass pricing and membership features](https://help.launchpass.com/en/articles/1548375-how-much-does-launchpass-cost)

## What is implemented

| Component | Behavior |
| --- | --- |
| Public collectors | Hyperliquid asset contexts and OKX funding/mark/open-interest endpoints; setup ingestion additionally supports closed candles, L2 books and a Coinbase spot reference |
| Setup Engine v1 | Frozen breakout/retest levels, volume and liquidity checks, prospective lifecycle, optional cross-venue context and branded cards; shadow collection is enabled by default; see `SETUP_ENGINE.md` |
| Units | Preserve source funding rates/intervals; compare in basis points per 8 hours; OI growth uses coin units to avoid counting price appreciation as new positions |
| Data health | Missing, nonfinite, stale, future, duplicate and inconsistent measurements fail closed |
| Event rules | Confirmed price/OI expansion, elevated funding, and cross-venue funding divergence |
| Noise control | Per-rule one-hour cooldown; six market alerts/hour across the universe by default |
| Alert follow-through | Five-minute sampled checks for up to 60 minutes, at most four updates per original alert, frozen rules and receipt-bound destinations; see `FOLLOW_THROUGH.md` |
| Paid summaries | 08:00 and 20:00 America/New_York, within a ten-minute scheduling window |
| Free sample | One daily BTC summary at 08:00 local time; no paid ETH/SOL measurements |
| Archive | Transactional SQLite observations, every generated event and its evidence, cycle health and delivery receipts |
| Delivery | Discord or Telegram, distinct audiences, opt-in sending, source-based message expiration, durable rate-limit backoff |
| Failure recovery | A send with an uncertain outcome is quarantined for operator review; no claim of exactly-once delivery |
| Operations | One-shot CLI, non-overlapping process lock, status/health check, backup/export, systemd timer |

The default requires two fresh venues before market comparisons are published. Missing one venue pauses that asset's analysis. Other healthy assets can continue. A degraded/recovered notice is archived and may be delivered to the paid destination. Failed reads never become zero funding, zero OI or invented prices.

Existing installations: use the pre-upgrade backup, schema-3 migration and rollout steps in [SETUP_ENGINE.md](SETUP_ENGINE.md). Setup collection starts in shadow mode; existing alert publishing is unchanged. The full visual gallery is [SETUP_PREVIEW.html](SETUP_PREVIEW.html).

## Run locally without publishing

Use a separate review checkout. No existing server files or processes need changing to test this code.

```bash
# Enter the repository checkout.
cd /opt/toknclaw
```

```bash
# Run the offline suite; no credentials, network access or posts.
python3 -m unittest discover -s market_watch/tests -v
```

```bash
# Collect one public-data cycle and preview generated messages; do not send.
python3 -m market_watch --config config/market_watch.json run
```

```bash
# Inspect source issues, collector age and delivery status.
python3 -m market_watch --config config/market_watch.json status
```

```bash
# Health test: nonzero means stale collection, source errors or failed/uncertain delivery.
python3 -m market_watch --config config/market_watch.json check
```

`run` performs one cycle. Use the timer below for repeated collection. It returns 2 on source degradation after archiving the cycle; that is not a successful market-data check. Approximately 15–18 minutes of archived history is needed for price/OI comparisons. Funding comparisons can become available sooner.

Generated events update cooldowns even in collection-only mode. This is intentional: turning on publishing never floods a channel with old archive entries. With configured destinations, unexpired pending messages from a previous preview cycle can be sent when `--send` is enabled. For a completely separate experiment, pass `--database /path/to/a/separate-test.sqlite3` before the subcommand.

## Source contracts and limits

- Hyperliquid: `metaAndAssetCtxs`; mark price, OI in base units, and hourly funding. The endpoint has no exchange event timestamp; the archive explicitly records `timestamp_basis=receipt`. A successful request proves retrieval time, not that the upstream has independently verified freshness. Venue outages that serve unchanged-but-stale responses need independent monitoring.
- OKX: exact `ASSET-USDT-SWAP` instrument match; `markPx`, `oiCcy`, `oiUsd`, `fundingRate`, component `ts` fields, `fundingTime` and `nextFundingTime`. The oldest component timestamp controls freshness. Missing interval metadata suppresses the observation. Zero funding is a valid observation and is never replaced with a next-period prediction.
- Normalization: `funding_rate * 8 / funding_interval_hours * 10000`. These are current rate estimates on a common time basis, not locked future payments or an annual yield promise.
- OKX mark prices are labeled USDT; Hyperliquid marks are labeled USD. The sanity comparison assumes a roughly dollar-pegged quote currency and rejects differences over 2%. This is not an executable cross-venue arbitrage model or an FX conversion feed.
- Regional OKX hosts are explicit through `okx_region`: `global`, `us`, `eea`, or `tr`. Global uses the officially recommended `openapi.okx.com`. Select the domain required for your account/region; there is no automatic endpoint hopping, proxy or location bypass.
- HTTP requests are bounded, redirects are rejected, response bodies and credentials never enter error logs. Source requests are retried by the next scheduled cycle; publishing handles explicit 429 backoff separately.
- No liquidation feed is implemented. Do not market OI/funding observations as measured liquidations or calibrated win probabilities.

Source references:

- [Hyperliquid asset contexts](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals)
- [Hyperliquid funding](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding)
- [OKX API documentation](https://www.okx.com/docs-v5/en/)
- [OKX API domain update, May 20, 2026](https://www.okx.com/docs-v5/log_en/#2026-05-20)

## Ubuntu 22.04 deployment

These commands create a separate application checkout, environment file, state directory and timer. They do not activate or modify ToknClaw's trading services. They are provided for an operator to run deliberately; the code review does not deploy anything.

```bash
# Enter the parent directory for the new isolated checkout.
cd /opt
```

```bash
# Create the Market Watch checkout; fails if this destination already exists.
sudo git clone --single-branch --branch feature/tokn-market-watch https://github.com/ToknNews/ToknClaw-Full_Backup.git /opt/tokn-market-watch
```

```bash
# Enter the new checkout.
cd /opt/tokn-market-watch
```

```bash
# Run the offline tests on the actual server interpreter.
python3 -m unittest discover -s market_watch/tests -v
```

```bash
# Create the root-only environment file only if one does not already exist.
sudo sh -c 'test ! -e /etc/tokn-market-watch.env && install -m 600 market_watch/market-watch.env.example /etc/tokn-market-watch.env'
```

```bash
# Enter channel credentials directly on the server; keep both delivery switches disabled initially.
sudoedit /etc/tokn-market-watch.env
```

Keep `MARKET_WATCH_ENABLE_DELIVERY=0` and `MARKET_WATCH_DELIVERY_ARGS=` for collection-only operation. Never paste tokens into GitHub, messages, screenshots, or shell history. The example file lists the exact environment variables. Paid/free Discord webhooks must belong to different channels; the code rejects the same webhook ID in both audiences. Two different webhooks that target the same channel cannot be detected locally, so verify the channel permissions and destination explicitly.

```bash
# Install the service only if no unit with this name is already present.
sudo sh -c 'test ! -e /etc/systemd/system/tokn-market-watch.service && install -m 644 market_watch/ops/tokn-market-watch.service /etc/systemd/system/tokn-market-watch.service'
```

```bash
# Install the timer only if no timer with this name is already present.
sudo sh -c 'test ! -e /etc/systemd/system/tokn-market-watch.timer && install -m 644 market_watch/ops/tokn-market-watch.timer /etc/systemd/system/tokn-market-watch.timer'
```

```bash
# Load the newly installed units.
sudo systemctl daemon-reload
```

```bash
# Start collection-only operation, recurring roughly every minute after each completed cycle.
sudo systemctl enable --now tokn-market-watch.timer
```

```bash
# Inspect recent source health and message previews; credentials are never printed.
sudo journalctl -u tokn-market-watch.service -n 40 --no-pager
```

```bash
# Run the explicit deployment health test against the durable service database.
sudo python3 -m market_watch --config config/market_watch.json --database /var/lib/tokn-market-watch/state.sqlite3 check
```

The service uses a systemd dynamic user, a private state directory, a read-only system view and no root application process. Only the Market Watch state directory is writable. An exit status of 2 is accepted by systemd to keep the collector scheduled, but `check` still exits nonzero for degraded health. Connect `check` to your uptime/operations monitoring; no external paging account is configured here.

### Deliberately activate a verified channel

First use a private test channel with no customers. After validating the venue data and destination, change the **complete environment file** using the supplied example as its schema. Set `MARKET_WATCH_ENABLE_DELIVERY=1` and `MARKET_WATCH_DELIVERY_ARGS=--send`, with the intended paid channel credentials. The next timer execution reads the updated file and publishes fresh pending/new messages. This is an explicit operational action, not a default behavior.

```bash
# Edit the private configuration only when ready for actual channel delivery.
sudoedit /etc/tokn-market-watch.env
```

To stop publishing while retaining collection, restore both delivery switches to their defaults. To stop this new collector entirely:

```bash
# Stop only the Market Watch timer and any currently running Market Watch cycle.
sudo systemctl stop tokn-market-watch.timer tokn-market-watch.service
```

## Paid access checklist

1. Make `#market-watch-paid` private: deny View Channel to `@everyone`; grant it to the membership provider's paid role and trusted operators only. Put free samples in a separate public channel.
2. Configure the hosted membership product: suggested demand test $29 first month, clearly disclosed renewal at $49. These are experiments, not validated prices.
3. Connect successful payments to the paid role. Verify cancellation, expiration, failed payment, refunds and access removal using the provider's supported test flow.
4. Test with an actual non-admin account. Verify it cannot read paid history or previews before purchase or after access ends. Verify that public channels cannot access paid content through inherited permissions.
5. Keep source APIs, SQLite files, event exports and operator interfaces private. This application opens no listening HTTP port and never exposes the existing ToknClaw API to subscribers.
6. Confirm source commercial display/redistribution rights and payment eligibility for the exact offer. Complete the necessary business review before selling recommendations. No unverified win-rate, return or "AI certainty" claims.
7. Require at least seven days of reliable collection, accurate samples and successful test-channel delivery before opening a paid pilot. Offline tests alone do not satisfy this gate.

The webhook publishes into an already gated channel. It does not verify or manage individual subscribers. Customer entitlement tests are a launch dependency and have not been performed by this implementation.

## Archive, backup and delivery recovery

Archive records are append-only at the application level, not cryptographically tamper-proof. SQLite observation/event writes and outbox creation share one transaction. Each outbox entry is bound to an audience and a fingerprint of the destination; secrets are not stored in SQLite. Rotating an endpoint does not silently reroute old entries.

Publication semantics are deliberately conservative: explicit 429s retry after their deadline, permanent errors fail, and network/5xx/receipt ambiguity becomes `unknown`. A process crash during sending also becomes `unknown`. Operators must check the destination before marking such a send delivered or discarding it. Blind retry could create duplicate notifications. This policy can drop an alert when delivery cannot be established; reliability claims must reflect that tradeoff.

```bash
# Enter the isolated deployment checkout.
cd /opt/tokn-market-watch
```

```bash
# Create a consistent backup at a NEW destination; existing backups are never overwritten.
sudo python3 -m market_watch --database /var/lib/tokn-market-watch/state.sqlite3 backup /var/lib/tokn-market-watch/backup-before-pilot.sqlite3
```

```bash
# Inspect uncertain delivery ids and redacted route names before resolving anything.
sudo python3 -m market_watch --database /var/lib/tokn-market-watch/state.sqlite3 status
```

```bash
# Inspect archived evidence locally; this may include paid content and is not a public endpoint.
sudo python3 -m market_watch --database /var/lib/tokn-market-watch/state.sqlite3 export --limit 20
```

Use `resolve-delivery --help` for the explicit `sent` or `discarded` resolution. A `sent` resolution requires the receipt/message ID verified in the channel. Archive files are not automatically deleted; monitor disk usage and take consistent backups. A running service may hold the lock briefly: retry a read/check after the cycle finishes instead of running a second collector.

## Validation and remaining launch work

The tests cover normalization, partial sources, current-schema input validation, stale/future data, no-lookahead baselines, native-unit OI, restart cooldowns, alert budgets, DST, audience boundaries, transaction rollback, rate limits, uncertain delivery, expiration and opt-in sending. Follow-through tests replay holding/faded/unavailable/recovered/expired states, frozen settings, migration, transaction rollback, restart deduplication, original-receipt gating, destination rotation and queue supersession.

A read-only check in the development environment retrieved the three configured Hyperliquid assets. OKX returned non-JSON content on both the older and officially recommended global endpoint, so the two-venue default correctly suppressed market comparisons. This is an unresolved deployment/source-access check, not grounds to substitute fabricated observations or bypass restrictions. Validate the appropriate regional source on the actual host before launch; a single-venue configuration is an explicit product-scope change and must be described as such to subscribers.

No real Discord/Telegram messages were sent, no memberships were sold, and no server was deployed during development. Destination receipts/access lifecycle and sustained runtime must be verified on the deployment environment.

## Position playbooks and historical outcomes

See [POSITION_PLAYBOOKS.md](POSITION_PLAYBOOKS.md) for conditional long/short/new-entry guidance, quantified funding budgets, directional changes during funding watches and the read-only `outcomes --days 30` report. These provide positioning context and descriptive mark outcomes; tested entry/stop/target scenarios and trading-return statistics are not implemented.
