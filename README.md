# Roblox Presence Monitor

Receive a notification when a connected Roblox account becomes online, so you can join them to play. Configure your own observing account and the connection you want to monitor. No particular relationship between the accounts is assumed.

The monitor runs on Linux with Python 3.11+ and its standard library. It can run in the foreground or under a service supervisor. Systemd and OpenRC deployment examples are included; the runtime does not depend on a specific distribution or service manager. Python's `ssl`, `sqlite3`, and `fcntl` modules must be available.

## How it works

- Validate the observer's authenticated identity, then request the configured connection's presence at a default 15-second interval. Online, in-game, and in-studio count as online.
- Send one notification for a new online session, including the first observed online state unless silent startup is selected.
- Require two consecutive valid offline observations before rearming. Network failures, expired sessions, missing results, and unknown presence types never count as offline.
- Persist transitions and a notification outbox in SQLite. Retry pushes separately from polling and preserve provider backoff across restarts.
- Pause online alerts while observations are failing or stale. Cancel unsent alerts after confirmed offline and expire undelivered online alerts after five minutes.
- Provide outage/recovery notifications and a local health command. No game locations, experience history, messages, or connections list are stored.

Detection takes about one polling interval after Roblox's API reports a change, plus request and push delivery time. Privacy behavior, caching, outages, and device settings can add delay. Transitions entirely between polls or during an outage can be missed. Delivery is not exactly once: a crash between provider acceptance and the local acknowledgement can cause a duplicate retry.

## Getting started

Clone or download the repository, open its directory in a terminal, and resolve the two account IDs:

```bash
cd Roblox-Presence
python3 -m roblox_presence resolve YourUsername
python3 -m roblox_presence resolve ConnectionUsername
```

Replace `YOUR_ACCOUNT_ID` and `CONNECTION_ACCOUNT_ID` below with the resulting numeric IDs:

```bash
python3 -m roblox_presence init --directory .local --observer-id YOUR_ACCOUNT_ID --target-id CONNECTION_ACCOUNT_ID --without-cookie
python3 -m roblox_presence --config .local/config.json set-cookie
python3 -m roblox_presence --config .local/config.json check
```

`init` creates private local configuration and a random notification topic. `set-cookie` asks for your own Roblox `.ROBLOSECURITY` value without echoing it. This session credential has account-level access: keep it in its protected file, outside Git, chat, command arguments, and screenshots. No credentials from the monitored connection are needed. The monitor does not automate login or change account protections or presence settings.

Run `check` while the connection is known to be online and compare it with Roblox. An authenticated offline result cannot distinguish actual offline from privacy-filtered visibility. Website visibility alone does not prove API visibility. The monitor respects the results available to your account and does not bypass hidden presence.

## Notifications

The default provider is [ntfy](https://ntfy.sh/). On a compatible phone, subscribe to the exact server and topic printed by:

```bash
python3 -m roblox_presence --config .local/config.json subscription
python3 -m roblox_presence --config .local/config.json test-push
```

On Android, allow notifications and the high-priority channel. Enable instant delivery where available and allow the required background operation. Confirm receipt with the screen locked and the phone idle, on both Wi-Fi and mobile data. See the [official Android delivery instructions](https://docs.ntfy.sh/subscribe/phone/). Delivery behavior differs between platforms and app builds; a provider acknowledgement is not proof of device receipt.

The free ntfy.sh topic is a randomly generated bearer secret, not an authenticated private channel. Anyone with its URL can read or publish to it, and the hosted provider processes/caches messages. Notifications omit account names and detailed activity; an online alert includes a profile link. Keep the topic private, or configure an authenticated ntfy server with `push.token_file`. Optional Pushover support is also available; its device client and account requirements are separate from the free ntfy setup.

## Running and deploying

```bash
# Foreground operation; Ctrl-C shuts down cleanly
python3 -m roblox_presence --config .local/config.json run

# Exit 0 means healthy; exit 1 means degraded or stale
python3 -m roblox_presence --config .local/config.json status

# Automated tests and an allowlisted source archive
python3 -m unittest discover -v
python3 tools/package.py
```

The account, credentials, notification destination, polling interval, and state directory are configuration choices. See [deployment options](docs/DEPLOYMENT.md) for systemd, OpenRC, or another supervisor; [design](docs/DESIGN.md) for failure behavior; and [verification](docs/VERIFICATION.md) for tested coverage and live checks.

Before continuous use, verify actual presence visibility and notification delivery with your own accounts and device. Test restarts and recovery on the intended host. Runtime portability does not mean every distribution or supervisor configuration has been tested.

API references are listed in [sources](docs/SOURCES.md). Keep operator-specific configuration, credentials, inventory, and deployment notes in ignored local files.
