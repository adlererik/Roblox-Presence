# Start here: what this does and how to install it

**Roblox Presence Monitor lets you know when a consenting Roblox connection comes online so you can choose to play together.** It is useful for friends, relatives, teammates, or any connection whose online status your own account is allowed to see.

Your always-on Linux server checks Roblox, normally about every 15 seconds. A notification service called ntfy delivers an alert naming the player and any visible game to your phone. Then you open Roblox yourself. Your laptop does not need to stay on, and the monitor never launches a game or joins one for you.

Version 0.3.0 adds a bookmarked private graph page. Open it on a phone or computer and tap **Generate new graph**. Its secret URL stays the same, and the latest snapshot remains until replaced. Daily `robox graph`, `robox dashboard`, `robox status` and `robox --help` commands need no sudo after one administrator setup. Follow the [dashboard guide](https://github.com/adlererik/Roblox-Presence/blob/v0.3.0/docs/DASHBOARD.md) and [activity/upgrade guide](https://github.com/adlererik/Roblox-Presence/blob/v0.3.0/docs/ACTIVITY.md).

The fourteen-day graph includes recorded online/offline times with seconds in the server's timezone, with visible unknown gaps. These are observation times, usually checked every fifteen seconds, not exact account login records. Recording starts with 0.2.0 or later; upgrades preserve it. Older activity cannot be recovered.

## Install it on your own server

Follow the [plain-language installation guide for v0.3.0](https://github.com/adlererik/Roblox-Presence/blob/v0.3.0/docs/GETTING_STARTED.md). It includes the commands, the device to use for each step, and the result to look for:

1. Connect to your own Linux server using your existing SSH login.
2. Download the reviewed release and check Python and the service manager.
3. Enter your own Roblox username and the consenting connection's username.
4. Authorize your own Roblox session through the protected terminal prompt, or an administrator-assisted phone Quick Sign In.
5. Install ntfy on your phone and subscribe to the exact private topic generated for your setup.
6. Confirm a test notification while the phone is locked, and compare the API with Roblox during a known online session.
7. Try a real online alert, then install the monitor as its own background service.
8. Enable the private dashboard once, bookmark its secret URL, and generate graphs from your phone.

You need Python 3.11 or newer. The automatic service installer needs systemd 250 or newer. The runtime is independent of server brand and Linux distribution; OpenRC and other supervisor instructions are separate. The phone setup uses ntfy, with Android menu instructions and links to other official clients. No particular family relationship, device model, hostname, network address, or operator account is built into the examples.

## Account access and privacy

This independent project is not endorsed by Roblox. It requires a full session credential for **your own account**, not the monitored connection's password. Read the account-risk explanation before authorizing it; no third-party monitor can promise zero account risk or perpetual access. Use official visibility settings and appropriate consent.

Each installation creates its own private configuration, credential files, and random notification topic. Never post them in GitHub issues, screenshots, chat, or a fork. The default ntfy topic is a secret address, not a password-protected channel; anyone with that address can read or publish to it. Push messages include the player’s display name, username, any game name shared by Roblox, and the server-local observation time. The notification provider and anyone with the topic can see these messages. Session cookies, numeric account IDs, and place/server IDs are never sent. Keep exported activity reports private too.

## Release status

[v0.3.0 is a preview release](https://github.com/adlererik/Roblox-Presence/releases/tag/v0.3.0). Automated tests, synthetic graph previews, authenticated status requests, systemd credential access, and locked-phone notification delivery have been exercised. A real known-online transition must still be verified on each installation; this preview does not claim completed end-to-end online-transition validation. An offline reply is insufficient to prove visibility. OpenRC's example is syntax checked, not live validated.

See the [README](https://github.com/adlererik/Roblox-Presence/blob/v0.3.0/README.md) for limits, account risks, troubleshooting, and secure session renewal. If asking for help, describe the error without posting private setup files or credentials.
