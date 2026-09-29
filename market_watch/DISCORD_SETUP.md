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

Scheduled publishing remains disabled. After the channel identity and permissions are verified, follow the main README's explicit activation step to enable market messages. A receipt for this connection test is not a receipt for a market alert. Preserve the archived observations while completing the private pilot and subscription/access tests.
