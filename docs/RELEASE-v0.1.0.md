# v0.1.0 — initial preview

Get a phone notification when a consenting Roblox connection appears online, so you can decide when to play together. The monitor runs on your own always-on Linux server; your laptop can be switched off. You open Roblox and join the connection yourself.

## Start here

- [Plain-language installation guide](https://github.com/adlererik/Roblox-Presence/blob/v0.1.0/docs/GETTING_STARTED.md): server and phone steps, commands, and expected results.
- [What it does and who it is for](https://github.com/adlererik/Roblox-Presence/blob/v0.1.0/docs/START_HERE.md).
- [Account risks, troubleshooting, and credential renewal](https://github.com/adlererik/Roblox-Presence/blob/v0.1.0/README.md).
- [OpenRC and other deployment options](https://github.com/adlererik/Roblox-Presence/blob/v0.1.0/docs/DEPLOYMENT.md).

## Included

- A Python standard-library runtime, with no extra Python packages.
- Configurable accounts and notification settings; ntfy is the free default path.
- Normal polling around every 15 seconds, with rate-limit backoff and explicit unknown/error handling.
- Persistent transitions and a bounded notification outbox to reduce repeated alerts across restarts.
- Protected session rotation, matching-account checks, and credential renewal.
- Optional phone Quick Sign In through a temporary sandboxed browser, provisioned separately.
- A dedicated systemd service with protected credentials, dynamic identity, restart supervision, watchdog, and resource limits.
- A separate OpenRC example and foreground support for other supervisors.
- Beginner instructions independent of any operator's relationships, account names, hardware, or network.

## Download and verify

Download both `roblox-presence-0.1.0.tar.gz` and `roblox-presence-0.1.0.tar.gz.sha256`. In their download directory, run:

```bash
sha256sum -c roblox-presence-0.1.0.tar.gz.sha256
tar -xzf roblox-presence-0.1.0.tar.gz
cd roblox-presence
```

The checksum must report `OK`. It checks that the downloaded archive matches the published checksum. A reviewed Git checkout is also supported by the installation guide.

The archive contains generic source, examples, tests, documentation, and Git exclusion rules. Private configuration, account sessions, notification topics, databases, setup helpers, logs, and Git history are excluded. GitHub's automatically generated source archives contain the tracked source tree only.

## Compatibility and validation

Linux and Python 3.11 or newer are required; the automated installer targets systemd 250 or newer. No specific server brand or distribution is required. Other service managers need the separate instructions and host validation. Phone setup uses ntfy's official clients; the documented notification-menu walkthrough covers Android.

The release is a **preview**, not a completed reliability certification. Automated tests cover transitions, delivery retries, session rotation, ACL-protected credentials, installation isolation, renewal, and packaging. Native systemd operation, authenticated status requests, and locked-phone delivery have been exercised. Real known-online detection and a full offline-to-online alert remain acceptance checks before reliance. OpenRC has syntax checks only; prolonged device idle, every network, and every client have not been certified.

## Account and delivery limits

This project is independent of Roblox and has no Roblox endorsement. It needs your own full account session and appropriate consent/visibility. It does not launch games, automate gameplay, send Roblox messages, or bypass privacy settings. Security challenges, session invalidation, API changes, outages, and phone settings can interrupt monitoring. Zero account risk and immediate delivery cannot be promised.

Hosted push services process generic messages and timing. The default unprotected ntfy topic is private only while its random address stays secret. Keep credentials, topics, private state, and operator details out of issues, screenshots, forks, and public uploads.
