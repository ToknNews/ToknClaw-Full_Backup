# Market Watch deployments from GitHub

Status: prepared for first installation. Offline tests validate command restrictions,
archive safety, backup preservation and failure recovery. Actual Hetzner SSH,
systemd execution and GitHub environment permissions must pass the connection
check and first release before this is considered operational.

## What this installs

The one-time installer is `market_watch/ops/deploy.py`. Run the reviewed, pinned
version as root with `install`. It creates:

| Item | Purpose |
| --- | --- |
| `tokn-deploy` | System account with no password login and a root-owned home |
| `/var/lib/tokn-market-watch-deployer/.ssh/authorized_keys` | A single public key restricted to the helper; no shell, PTY or forwarding |
| `/usr/local/libexec/tokn-market-watch-deploy.py` | Root-owned, standalone standard-library helper |
| `/etc/sudoers.d/tokn-market-watch-deploy` | Only the helper's probe and validated release command |
| `/var/lib/tokn-market-watch-deployment` | Root-only logs, receipts, source mirror and backups |
| `/opt/tokn-market-watch-releases` | Root-owned release directories |

Installation does not change the running application, its timer, configuration,
database, environment file or existing SSH accounts. It refuses to overwrite an
existing installation. An interrupted installation needs inspection before retry;
do not delete existing paths to force a reinstall.

Only a deployment writes the complete managed systemd drop-in at
`/etc/systemd/system/tokn-market-watch.service.d/90-managed-release.conf`.
The original `/opt/tokn-market-watch` checkout remains in place. Runtime code is
selected by the drop-in, while configuration stays at
`/opt/tokn-market-watch/config/market_watch.json`, credentials stay at
`/etc/tokn-market-watch.env`, and the live archive stays at
`/var/lib/tokn-market-watch/state.sqlite3`.

## 1. Create a dedicated key on your Mac

Use a new Mac Terminal tab, not the tab connected to Ubuntu. The private key is
unencrypted so GitHub Actions can use it without a human prompt. It has its own
limited server account. Do not reuse your administrator key. If ssh-keygen asks
to overwrite an existing file, answer `n` and stop.

```bash
# Work in your Mac home directory.
cd ~
```

```bash
# Create the dedicated Actions key; never paste its private contents into chat.
ssh-keygen -t ed25519 -f "$HOME/.ssh/tokn_market_watch_actions" -C tokn-market-watch-actions -N ""
```

## 2. Install on Ubuntu through your existing SSH session

Use your existing root session. Download the installer from the exact reviewed
commit, not a moving branch. Replace `REVIEWED_COMMIT_SHA` with that full SHA.
The assistant supplies the exact URL and SHA-256 checksum for the reviewed file.
If a command fails, stop rather than continuing with a missing or old download.

```bash
# Work from the server administrator's home directory.
cd /root
```

```bash
# Create a new private setup folder; an existing folder causes a stop.
mkdir -m 700 tokn-deploy-setup
```

```bash
# Work in the newly created setup folder.
cd /root/tokn-deploy-setup
```

```bash
# Download the reviewed installer without executing remote output.
curl --fail --show-error --silent --location https://raw.githubusercontent.com/ToknNews/ToknClaw-Full_Backup/REVIEWED_COMMIT_SHA/market_watch/ops/deploy.py --output deploy.py
```

```bash
# Display the checksum and compare with the exact one supplied for the release.
sha256sum deploy.py
```

```bash
# Explicitly create the restricted deployment account and helper.
sudo python3 -I deploy.py install
```

The installer asks for a **public** key. While it is waiting, run the following
in your **Mac tab**, then return to the Ubuntu tab, paste and press Enter:

```bash
# Copy only the public key to your Mac clipboard.
pbcopy < "$HOME/.ssh/tokn_market_watch_actions.pub"
```

Expected output includes `"status": "installed"`, followed by a line beginning
`tokn-market-watch ssh-ed25519`. Keep that public host-identity line for GitHub.
Do not share your environment file, private key or full service logs in chat.

## 3. Test the restricted account from your Mac

Use the same public server address used for your working root connection.
The host key should already be known from that connection. Do not bypass host
key verification or accept a changed fingerprint without checking it.

```bash
# Stay in your Mac home directory.
cd ~
```

```bash
# Connection-only test; it does not deploy or send a Discord message.
ssh -T -o IdentitiesOnly=yes -i "$HOME/.ssh/tokn_market_watch_actions" tokn-deploy@YOUR_SERVER_PUBLIC_IP probe
```

Expected: `"status": "connection_verified"` and `"application_changed": false`.
This verifies the Mac-to-server route, not GitHub-hosted runner connectivity.

## 4. Add the GitHub deployment environment

Open the repository's **Settings → Environments → New environment** and create
`market-watch-production`.

For **Deployment branches and tags**, choose **Selected branches and tags**.
Add these two rules, each with type **Branch**:

- `ops/market-watch-connect`
- `release/market-watch`

Create the following **environment secrets**, not plaintext repository files:

| Secret | Value |
| --- | --- |
| `TOKN_SSH_HOST` | Your server's public IP or DNS hostname, without `root@`, a protocol or a port |
| `TOKN_SSH_KEY` | Complete private deployment key, including its BEGIN/END lines |
| `TOKN_KNOWN_HOSTS` | The complete `tokn-market-watch ssh-ed25519 ...` line printed by the installer |

Copy the private key directly to the GitHub secret form from your Mac:

```bash
# Copy the deployment key to paste directly into GitHub's secret form.
pbcopy < "$HOME/.ssh/tokn_market_watch_actions"
```

If SSH uses a port other than 22, add an environment **variable** named
`TOKN_SSH_PORT` containing the port number. The username is fixed to `tokn-deploy`.
No Hetzner API token, root password or Discord webhook goes into this workflow.

## 5. Verify from GitHub before releasing

Tell the assistant that installation and secrets are ready. It can then publish
the reviewed commit on `ops/market-watch-connect`. The workflow tests the code
without production secrets, then authenticates and runs only `probe`.

The feature branch and pull requests never trigger deployment. This workflow
uses branch pushes, so it does not require a manual-dispatch workflow on `main`.
If GitHub connectivity fails, inspect the SSH key/host identity and firewall
rules. A firewall permitting only your Mac's IP will not permit hosted runners.
Do not open unrelated ports or disable host verification as a shortcut.

Once the probe passes and a release is authorized, advance `release/market-watch`
to the tested commit without a force push. Both GitHub and the server test that
version; the server independently fetches the current release branch and rejects
any other SHA. A superseded queued release fails before the service is stopped.

## Release behavior and recovery

1. Fetch/export only `market_watch/` and the repository's non-secret sample config
   into a new root-owned directory. Reject links, traversal and special files.
2. Run offline tests in an isolated systemd dynamic-user service with networking
   disabled and without production credentials. Application tests never run as root.
3. Pause the timer and worker. Make a consistent SQLite backup, validate it, and
   save exact copies of configuration, environment and previous release selection.
4. Replace the complete helper-owned drop-in, reload systemd and run a real cycle
   under the existing application service and its existing delivery settings.
5. Run the read-only health check under a dynamic user. Resume the timer.

Existing delivery settings continue to apply, so a real release cycle may send
normal enabled alerts. Installation and `probe` never collect or send messages.
The deployment does not enable setup publishing or change any market settings.
An old configuration without setup fields keeps the setup engine disabled until
an explicit configuration change. Existing CLI examples using the old checkout
must use the **active service working directory** after the first managed release.

| Result | Behavior |
| --- | --- |
| Test/ref/archive failure | Current application and schedule untouched |
| Backup failure before cutover | Previous schedule resumed; code not switched |
| Healthy cycle/check | Workflow passes; new release and timer active |
| Data-health check exits 2 | Workflow fails as `deployed_degraded`; collection continues for recovery |
| Hard failure after cutover | Timer paused; new database/receipts preserved; forward correction required |
| SSH client disconnect | Root systemd deployment worker continues; inspect saved receipt |

No automatic database restoration occurs: a rollback could erase newer delivery
receipts and cause duplicate notifications. A pre-schema-3 application cannot
read a schema-3 archive. Prefer a forward correction; a deliberate restore needs
receipt reconciliation. Backups and old releases are retained without automatic
pruning and consume disk; review retention before sustained frequent deployments.
Power loss or a killed deployment worker also requires inspecting the receipt and
actual service state before another deployment.

Read-only operator checks on the Ubuntu server:

```bash
# Work from the existing application directory.
cd /opt/tokn-market-watch
```

```bash
# Show the saved deployment result without credentials.
sudo cat /var/lib/tokn-market-watch-deployment/latest.json
```

```bash
# Find the actual code directory selected for the running service.
sudo systemctl show tokn-market-watch.service --property=WorkingDirectory
```

```bash
# Verify the recurring schedule.
sudo systemctl list-timers --all tokn-market-watch.timer --no-pager
```

The trusted helper does not update itself during a release. Helper changes need
their own explicit reviewed installation. To revoke access, remove this one
deployment public key or its sudoers rule through a deliberate administrator
change; do not delete existing personal SSH keys.

References checked October 4, 2026:

- https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments
- https://docs.github.com/en/actions/concepts/security/secrets
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- https://man.openbsd.org/sshd.8
