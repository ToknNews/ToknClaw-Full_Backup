# Alert follow-through

New paid alerts now receive a persistent watch. Updates use the existing Discord/Telegram delivery system and reference the original alert's `Watch ref`. This is sampled condition tracking, not trade execution, a stop-loss system or a performance claim.

## Subscriber behavior

| Card | Meaning | What happens next |
| --- | --- | --- |
| CONDITION HOLDS | Fresh observations still meet the original rule at this check | Continue checking; unchanged checks are quiet |
| TRADE READ CHANGED · CONDITION HOLDS | The funding rule still qualifies, but the separate price/OI directional scenario changed | Reassess direction independently of carry; consumes an update slot |
| CHECK PAUSED | Required observations, instruments or price/OI baselines cannot be verified | Keep the watch open for recovery or expiry |
| COVERAGE BACK · CONDITION HOLDS | A previously unavailable watch is observable and meets the original rule again | Resume normal checks |
| CONDITION FADED | A valid comparison no longer meets the original rule | Close this watch; it never reopens |
| WATCH ENDED | The time window or update limit ended tracking | Close the watch and state the latest available condition |

The first due check can be holding, faded or unavailable. A recovery that no longer meets the rule closes as CONDITION FADED. A future qualifying initial alert starts its own watch subject to existing cooldowns and alert limits.

Every update identifies the original event, original date/time, actual check date/time, elapsed time and sequence. When measurements are valid, it shows separate venue readings and changes since the original mark/OI/funding values. Unavailable updates withhold partial venue numbers and do not infer a market outcome.

Price/OI rules still compare a rolling lookback of approximately 15 minutes by default. Since-original changes use the initial alert's measurements. These are different comparisons: a rolling condition can fade while price remains above its initial mark. Neither mark change represents a customer's executed return. Holdings between sampled checks are not established.

Position updates distinguish long/short continuation, faded conditions, unobservable data and expiry. Funding updates include a current price/OI scenario and carry budget. A first follow-up compares direction with the original playbook when available; older watches without that field remain compatible. See `POSITION_PLAYBOOKS.md`.

## Defaults and frozen settings

| Setting | Default | Validation |
| --- | --- | --- |
| `followup_enabled` | `true` | Boolean |
| `followup_check_minutes` | `5` | Integer, at least 1, less than horizon |
| `followup_horizon_minutes` | `60` | Integer, at most 240 |
| `followup_max_updates` | `4` | Integer, 2–10; includes closure |

Each initial alert captures its thresholds, rule version, venue/instrument cohort, comparison cohort, freshness tolerances, watch horizon, check interval and update cap. Later configuration edits apply to new watches. Existing watches keep those original settings. The current `followup_enabled` switch is a global exception: setting it false closes active watches locally and expires their queued updates without sending closure messages. Re-enabling does not reopen them.

Checks run on the first collector cycle at or after their due time. The next check is scheduled from the actual check time; missed intermediate checks are not replayed. A watch requires the entire original venue cohort, even when the initial configured minimum was smaller. Source and fetch timestamps must advance beyond the last valid cohort reading; this does not overcome the upstream freshness limitation of Hyperliquid receipt timestamps.

The cap counts generated follow-up events, including events that were not deliverable. If another state change or directional-scenario change would consume the last slot, it becomes a closing WATCH ENDED update instead of promising further tracking. A valid fade closes immediately. An unchanged condition can remain under observation until the horizon, with the closing slot reserved. This cap is separate from the existing six initial market alerts/hour; it is not a claim that all message types together are capped at six/hour.

A closing check can arrive up to the original `max_age_seconds` after the horizon (180 seconds by default). The card always shows its actual time and elapsed minutes. A later return archives an unavailable expiry, closes the watch and sends no catch-up message. It never substitutes a much later price for the missing closing checkpoint.

## Delivery and archive integrity

- The original alert must have a confirmed `sent` receipt at the exact route fingerprint before that route can receive a follow-up. Pending, failed, expired, unknown and unconfigured original destinations do not qualify.
- A new destination or rotated webhook does not inherit historical watches. Free destinations never receive these updates.
- Follow-up events are archived even if no route is eligible. Creating a route later does not replay that archive.
- New states expire pending older follow-ups for the same watch, including updates waiting after HTTP 429. A send with an unknown outcome stays quarantined for operator review and is never blindly repeated.
- Follow-ups retain the existing explicit send gates, freshness deadlines, receipt checks and rate-limit handling. These can suppress or miss a notification; there is no exactly-once or complete-delivery guarantee.
- Observation writes, watch state, generated events, superseded queue entries and new outbox rows commit in one collector transaction. A failed cycle rolls them back together. The process lock and SQLite unique keys protect restart behavior.
- `status` and `check` include `watches` counts. The `states` counts include both open and closed history; `active` and `closed` distinguish them. `last_check` preserves the latest evaluation. State-change event evidence and the underlying observations remain archived.

## Upgrade an existing server

This update migrates archive schema 1 to schema 2 on the first write. It adds `alert_watches` and `alert_followups`; it does not rewrite or delete existing observations, events or receipts. Read-only checks and backups support either schema. It starts watches only for newly generated alerts.

Use the existing private-channel pilot. These commands explicitly pause the service, create a consistent backup, update code, test, then resume publishing under the existing environment settings. Stop if a command fails. If the backup destination already exists, choose a new filename; do not overwrite it.

```bash
# Enter the installed project.
cd /opt/tokn-market-watch
```

```bash
# Pause the scheduled worker while updating code and taking the backup.
sudo systemctl stop tokn-market-watch.timer tokn-market-watch.service
```

```bash
# Save a consistent pre-migration copy at a new destination.
sudo python3 -m market_watch --database /var/lib/tokn-market-watch/state.sqlite3 backup /var/lib/tokn-market-watch/pre-followthrough.sqlite3
```

```bash
# Download the follow-through implementation.
git pull --ff-only origin feature/tokn-market-watch
```

```bash
# Run offline verification without sending any messages.
python3 -m unittest discover -s market_watch/tests -v
```

```bash
# Migrate and run one collection cycle with the existing publishing setting.
sudo systemctl start tokn-market-watch.service
```

```bash
# Resume the recurring schedule after the one-shot service succeeds.
sudo systemctl start tokn-market-watch.timer
```

```bash
# Confirm source/delivery health and inspect watch counts.
sudo python3 -m market_watch --config config/market_watch.json --database /var/lib/tokn-market-watch/state.sqlite3 check
```

A `watches.active` value of zero is normal until a new qualifying alert is generated. A follow-up is eligible after its original message has a receipt and the first check is due. Verify the shared reference and layout in Discord during the private pilot. A stopped in-flight send may appear as unknown; inspect the channel before resolving it using the existing delivery recovery procedure.

### Reverting behavior

Disable follow-through with `followup_enabled: false` in a complete, validated configuration, retaining this version of the code. The next collector cycle closes active watches and expires their queued follow-ups. Original collection, alert rules and briefs continue.

Older releases accept schema 1 only and cannot operate directly on the migrated database. Do not silently restore an old database over newer observations or receipts: that can lose history and change delivery behavior. Retain the migrated archive and resolve a code issue forward where possible. Any actual database restoration requires a deliberate recovery plan that accounts for deliveries since the backup.

## Offline preview

```bash
# Enter the installed project.
cd /opt/tokn-market-watch
```

```bash
# Print a fictional faded-condition update without network access or database writes.
python3 -m market_watch.message_preview --kind followup_faded
```

The HTML preview includes six follow-up alternatives plus the nine existing examples. These are independent fictional scenarios, not one chronological watch. All carry a DEMO label. Visual wrapping must still be checked in the real Discord client.
