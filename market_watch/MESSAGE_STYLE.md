# Tokn Market Watch message system

## Existing Tokn identity

New Discord messages use the original Tokn coin as the webhook avatar and author icon, with the sender name **Tokn Market Watch**. Alerts and follow-ups add a coin thumbnail. Scheduled paid briefs and the free sample include the existing circuit-board banner after their evidence. Data-health cards use the small icon alone to stay compact.

The primary accent is **Tokn electric blue `#2D73FF`**, taken from the existing global CSS (`rgba(45,115,255,...)`). Rose, amber, violet, slate and mint retain their message/status meanings. Discord controls native card backgrounds and fonts; no custom CSS is sent to Discord. The preview's navy page frame is presentation only. No additional paid API, host, image generation or rendering service is required.

Assets come from `ToknNews/ToknNews-Full_Backup` at commit `70fcd4b37147acbb34294b5086d597d7d04bf2ce`. See `assets/README.md` for exact original paths and checksums. Images are reused unchanged. Production embeds reference commit-pinned public GitHub media URLs (these source files use Git LFS); do not substitute raw pointer-file URLs. Discord fetches the art. The worker does not download images or send secrets to the image host. Keeping those public source assets available is required for artwork rendering; market evidence remains text in the embed. Local copies make the preview fully offline.

## Voice and hierarchy

Use a direct, slightly informal market-desk voice. Lead with a useful interpretation, then explain what the reader should check and show the evidence. **The read** identifies a conditional bullish/bearish continuation scenario or says direction is unconfirmed. **Position playbook** separates existing long, existing short and new-entry considerations. **What changes the read** shows the actual configured thresholds and what would make each condition stop qualifying. Funding budgets quantify carrying-cost exposure on a standard notional. These are snapshot conditions, not validated trade entry, stop-loss or profit-target levels.

Every market alert uses this order:

1. Tokn brand and asset/event headline.
2. Short hook, time window, venue/baseline coverage and New York timestamp.
3. The read.
4. Position playbook: long, short and new entry; funding-gap cards also compare the cost of changing venues.
5. What changes the read, separating the original funding condition from any directional price/OI scenario. Funding alerts also show a standardized carry budget.
6. Separate Hyperliquid and OKX measurements, and funding gap where relevant.
7. A compact units/method note.

Briefs start with **At a glance**: an asset-by-asset description of the current price/OI rule context and any funding conditions, before the detailed readings. Missing coverage pauses analysis; missing price/OI baselines are distinguished from a valid comparison with no qualifying pattern. Funding can still be described when its current measurements are valid.

Do not invent confidence scores, win rates, liquidations, whale activity, support/resistance, net new longs/shorts or a causal explanation. A price/OI pattern can justify closer attention; it does not establish future returns. Funding comparisons describe estimated carry, not executable arbitrage. Automatic follow-through is implemented separately in `followups.py`; its timing, state meanings, delivery limits and upgrade steps are documented in `FOLLOW_THROUGH.md`.

Discord uses one native embed with vertically stacked fields. Telegram and the event archive retain readable plain text with the same measurements and interpretations. No generated artwork or paid model calls are needed.

## Message types

| Type | Headline example | Accent | Contents |
| --- | --- | --- | --- |
| Price/OI expansion | BTC · PRICE ↑ / OI ↑ | Tokn blue | Price up, coin-unit OI up, venue readings and conditional interpretation |
| Price decline/OI expansion | BTC · PRICE ↓ / OI ↑ | Rose | Price down, coin-unit OI up; no promise of continued downside |
| Elevated positive funding | BTC · LONGS PAYING UP | Amber | Positive funding estimates, price/OI context where available |
| Elevated negative funding | BTC · SHORTS PAYING UP | Amber | Negative funding estimates, without asserting a rebound |
| Funding divergence | BTC · FUNDING SPLIT | Violet | Venue rates plus their difference in basis points |
| Follow-up | BTC · CONDITION HOLDS / CONDITION FADED / CHECK PAUSED / WATCH ENDED | Tokn blue / Slate / Amber | Original reference, actual check time, rolling rule status and separate changes since the original alert |
| Paid brief | AM BRIEF / PM BRIEF | Tokn blue | BTC, ETH and SOL sections, an opening interpretation, source coverage, available price/OI changes |
| Public sample | FREE LOOK · BTC | Slate | BTC measurements only, plus a short description of full-feed coverage |
| Data health | DATA CHECK · COVERAGE LIMITED / RESTORED | Amber / Mint | Affected coverage and whether measurements can be used |

Colors identify event types, not confidence, trade direction, or expected returns. Initial alert, health and brief triggers are unchanged. Funding follow-ups now also report changes in the separate price/OI scenario, within the existing update cap. The existing thresholds, cooldowns, audience routes and scheduled windows continue to apply.

The interpretation logic, read-only outcome report and path to tested entry/exit scenarios are documented in `POSITION_PLAYBOOKS.md`.

## Data conventions

- Keep USD and USDT prices labeled separately; do not invent an aggregated executable price.
- Display funding as a signed percentage on an equivalent 8-hour basis. One basis point is 0.01 percentage points; `1.2 bps` renders as `+0.0120% / 8h eq.`. Actual venue settlement intervals may differ and estimates can change.
- Display OI dollar notional separately from percentage changes in OI coin units. Price appreciation alone is not an increase in coin-unit OI.
- Include **Received** for Hyperliquid receipt-based timestamps and **As of** for OKX source timestamps. Source times are explicitly UTC; the card's human-readable timestamp follows the configured timezone.
- Price/OI changes use valid archived baselines around the configured lookback. If a brief lacks one, say it needs a valid baseline; never substitute zero.
- Withhold an asset's numbers in the brief if fresh coverage is insufficient. A free sample excludes other assets' measurements, comparison history and source-specific issues from its card.
- Use measured values, fixed templates and deterministic arithmetic. The message formatter does not call an LLM.

The subscriber-value roadmap and validation experiment are in `SUBSCRIBER_VALUE.md`.

## Preview

`MESSAGE_PREVIEW.html` is a self-contained, responsive design preview with a selector for fifteen examples, including six follow-up alternatives. All example values and timestamps are fictional and each card is labeled DEMO. It has no credentials, network requests, trackers or posting controls. It embeds all three original images. Its layout is illustrative; Discord's exact typography, wrapping and image placement vary by device and theme.

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

If follow-through is already installed and the database is at schema 2, this branding update needs no further migration. If upgrading from before follow-through, first use `FOLLOW_THROUGH.md`, which includes the required pre-migration backup.

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
# Fast-forward to the tested branding update.
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

Presentation is stored in event evidence. Branding uses presentation format `tokn-card-v2`; the database remains schema 2. Existing archived/pending v1 cards keep their original formatting and sender behavior. Previously posted messages are not edited. New v2 cards override the sender name/avatar per message, without changing the webhook configuration. A message appears only when a real alert or brief is due. Verify the first new Discord card and its receipt in the private channel before expanding access.

## Payload checks

Discord presentation is a restricted embed: title, description, author, stacked fields, footer, color and timestamp. V2 additionally permits only the exact approved Tokn author icon, coin thumbnail and banner URLs. Arbitrary image URLs, redirects via query strings, extra link fields and unpinned branch URLs are rejected. Legacy v1 remains link-free. Both versions are validated against field and total character limits before sending. Allowed mentions remain empty and `wait=true` still supplies a delivery receipt. Oversized or malformed cards fail closed instead of dropping evidence through truncation. Telegram gets the plain-text version without Discord formatting syntax.

Official API references:
- https://docs.discord.com/developers/resources/webhook#execute-webhook
- https://docs.discord.com/developers/resources/message#embed-object-embed-limits
