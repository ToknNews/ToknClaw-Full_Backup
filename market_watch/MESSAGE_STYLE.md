# Tokn Market Watch message system

## Voice and hierarchy

Use a direct, slightly informal market-desk voice. The headline states what the data shows. Venue readings provide the evidence. **The read** explains the observation without turning it into an entry or a forecast. **Watch next** identifies what measurement would change the interpretation. Avoid invented confidence scores, win rates, liquidation counts, whale activity and claims about who is opening positions.

Every market alert uses this order:

1. Tokn brand and asset/event headline.
2. Short hook, time window, venue coverage and New York timestamp.
3. Separate Hyperliquid and OKX measurements.
4. The read.
5. Watch next.
6. A compact units/method note.

Discord uses one native embed with vertically stacked fields. Telegram and the event archive retain readable plain text with the same measurements and interpretations. No generated artwork or paid model calls are needed.

## Message types

| Type | Headline example | Accent | Contents |
| --- | --- | --- | --- |
| Price/OI expansion | BTC · PRICE ↑ / OI ↑ | Cyan | Price up, coin-unit OI up, venue readings and conditional interpretation |
| Price decline/OI expansion | BTC · PRICE ↓ / OI ↑ | Rose | Price down, coin-unit OI up; no promise of continued downside |
| Elevated positive funding | BTC · LONGS PAYING UP | Amber | Positive funding estimates, price/OI context where available |
| Elevated negative funding | BTC · SHORTS PAYING UP | Amber | Negative funding estimates, without asserting a rebound |
| Funding divergence | BTC · FUNDING SPLIT | Violet | Venue rates plus their difference in basis points |
| Paid brief | AM BRIEF / PM BRIEF | Cyan | BTC, ETH and SOL sections, source coverage, available price/OI changes |
| Public sample | FREE LOOK · BTC | Slate | BTC measurements only, plus a short description of full-feed coverage |
| Data health | DATA CHECK · COVERAGE LIMITED / RESTORED | Amber / Mint | Affected coverage and whether measurements can be used |

Colors identify event types, not confidence, trade direction, or expected returns. No alert, health or brief trigger was added to manufacture messages for this styling change. The existing thresholds, cooldowns, audience routes and scheduled windows continue to apply.

## Data conventions

- Keep USD and USDT prices labeled separately; do not invent an aggregated executable price.
- Display funding as a signed percentage on an equivalent 8-hour basis. One basis point is 0.01 percentage points; `1.2 bps` renders as `+0.0120% / 8h eq.`. Actual venue settlement intervals may differ and estimates can change.
- Display OI dollar notional separately from percentage changes in OI coin units. Price appreciation alone is not an increase in coin-unit OI.
- Include **Received** for Hyperliquid receipt-based timestamps and **As of** for OKX source timestamps. Source times are explicitly UTC; the card's human-readable timestamp follows the configured timezone.
- Price/OI changes use valid archived baselines around the configured lookback. If a brief lacks one, say it needs a valid baseline; never substitute zero.
- Withhold an asset's numbers in the brief if fresh coverage is insufficient. A free sample excludes other assets' measurements, comparison history and source-specific issues from its card.
- Use measured values, fixed templates and deterministic arithmetic. The message formatter does not call an LLM.

## Preview

`MESSAGE_PREVIEW.html` is a self-contained, responsive design preview with a selector for nine message types. All example values and timestamps are fictional and each card is labeled DEMO. It has no credentials, network requests, trackers or posting controls. Its layout is illustrative; Discord's exact typography and wrapping vary by device.

```bash
# Enter the installed project.
cd /opt/tokn-market-watch
```

```bash
# Print a clearly labeled fictional alert without network access or database writes.
python3 -m market_watch.message_preview --kind price_oi_up
```

```bash
# Inspect the fictional morning brief as plain text.
python3 -m market_watch.message_preview --kind am_brief
```

```bash
# Inspect the demo Discord payloads without publishing.
python3 -m market_watch.message_preview --format json
```

## Rollout to the private feed

These steps pause collection briefly so a running process cannot import a mixture of old and new files. They preserve the runtime configuration, webhook, database and delivery switches. Stop if any command fails; do not resume with failing tests.

```bash
# Enter the deployed checkout.
cd /opt/tokn-market-watch
```

```bash
# Pause only the Market Watch timer and worker during the update.
sudo systemctl stop tokn-market-watch.timer tokn-market-watch.service
```

```bash
# Fast-forward to the tested formatting update.
git pull --ff-only origin feature/tokn-market-watch
```

```bash
# Verify the updated package on the server, without sending messages.
python3 -m unittest discover -s market_watch/tests -v
```

```bash
# Resume the existing schedule with the existing delivery setting.
sudo systemctl start tokn-market-watch.timer
```

```bash
# Run one cycle and wait for completion.
sudo systemctl start tokn-market-watch.service
```

```bash
# Confirm live source health and absence of unresolved delivery failures.
sudo python3 -m market_watch --config config/market_watch.json --database /var/lib/tokn-market-watch/state.sqlite3 check
```

New events carry the new presentation in their existing evidence record; no database migration is required. Existing archived/pending events keep their original text. A message appears only when a real alert or brief is due. Verify the first new Discord card and its receipt in the private channel before expanding access.

## Payload checks

Discord presentation is a restricted, link-free embed: title, description, author name, stacked fields, footer, color and timestamp. It is validated against field and total character limits before sending. Allowed mentions remain empty and `wait=true` still supplies a delivery receipt. Oversized or malformed cards fail closed instead of dropping evidence through truncation. Telegram gets the plain-text version without Discord formatting syntax.

Official API references:
- https://docs.discord.com/developers/resources/webhook#execute-webhook
- https://docs.discord.com/developers/resources/message#embed-object-embed-limits
