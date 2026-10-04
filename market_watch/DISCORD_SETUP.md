# Private Discord connection test

Run this after the systemd collector is healthy and after creating a private Discord text channel visible only to trusted operators. Create a webhook for that exact channel. Keep its URL out of chat, screenshots, GitHub and command arguments.

The helper reads the root-only `/etc/tokn-market-watch.env` file. `configure` backs up that file and atomically replaces it with a complete configuration preserving its settings and adding the private test-channel webhook to the paid route. Both scheduled delivery switches must remain disabled; the helper refuses to configure or test an active publisher. It accepts the unquoted format of the shipped example and refuses unsupported/duplicate settings rather than interpreting shell content.

```bash
# Enter the deployed checkout.
cd /opt/tokn-market-watch
```

```bash
# Fetch the tested setup helper without overwriting divergent local work.
git pull --ff-only origin feature/tokn-market-watch
```

```bash
# Verify the updated package on the actual server; no external requests or messages.
python3 -m unittest discover -s market_watch/tests -v
```

```bash
# Paste the private test-channel webhook at the hidden prompt and press Enter.
sudo python3 -m market_watch.discord_setup configure
```

```bash
# Preview the exact connection-test text without sending.
sudo python3 -m market_watch.discord_setup test
```

```bash
# Explicitly send one labeled setup message to the configured private test channel.
sudo python3 -m market_watch.discord_setup test --send
```

A successful response has `status: sent` and a Discord `message_id`. Verify that exact message appears in the intended private channel. This tests the production HTTP and Discord adapter; it does not collect market data or prove the scheduled publisher's end-to-end operation. The helper writes receipt state into a separate root-only archive at `/var/lib/tokn-market-watch-setup/discord-test.sqlite3`; it does not add synthetic measurements to the production database.

Rerunning a successful test returns its existing receipt without sending a duplicate. An interrupted or ambiguous send returns `unknown` and blocks further sends to that same webhook; inspect Discord before any operator reconciliation. A definite rejection returns `failed`. A 429 records a retry deadline and cannot be retried before that deadline. Do not delete the test archive to bypass uncertain delivery. Rotating to a different webhook creates a separate test identity.

## Activate the verified private feed

After verifying the test message in the intended private channel, run the following explicit activation command. It requires a successful saved connection-test receipt for the configured webhook and exactly one Discord paid/test route. It backs up and atomically replaces the private environment file, changing both scheduled-delivery switches together. It does not test Discord channel permissions; verify those in Discord before activation.

```bash
# Enter the installed project.
cd /opt/tokn-market-watch
```

```bash
# Enable actual scheduled market messages to the verified private channel.
sudo python3 -m market_watch.discord_setup enable
```

The next timer invocation reads the new settings; no daemon reload is required for an environment-file change. The following command waits for one service cycle, coalescing with a cycle already in progress. A cycle already running at activation may still have the old environment; the next scheduled cycle will use the new file.

```bash
# Start one collection/publishing cycle and wait for completion.
sudo systemctl start tokn-market-watch.service
```

```bash
# Inspect recent cycle output for sending_enabled and delivery outcomes.
sudo journalctl -u tokn-market-watch.service -n 100 --no-pager -o cat
```

```bash
# Check source health and delivery failures against the production archive.
sudo python3 -m market_watch --config config/market_watch.json --database /var/lib/tokn-market-watch/state.sqlite3 check
```

No market message is guaranteed immediately: events require qualifying market conditions, or the configured 08:00/20:00 America/New_York digest window. The connection-test receipt lives in a separate archive and does not count as a market-message delivery. Confirm actual market content and receipts during the private pilot before opening paid access.

To pause publishing while collection continues:

```bash
# Disable publishing for future service invocations; retain the webhook and data collection.
sudo python3 -m market_watch.discord_setup disable
```

A cycle already running may finish a send with settings it previously loaded. If an immediate stop is needed, use the main README's command to stop both the timer and service. Do not rerun the connection test against an active publisher; it is restricted to collection-only mode.
