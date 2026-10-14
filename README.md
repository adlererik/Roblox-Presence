# Roblox Presence Monitor

Receive a phone notification when a Roblox connection comes online, then open Roblox yourself to play together. The monitor runs on an always-on Linux computer. Your phone receives notifications. A workstation does not need to stay on for monitoring.

This is an independent project, without Roblox endorsement or approval. It needs your own Roblox account's session credential. It does not need the other person's password or session.

## Can this get my Roblox account banned?

**No one can promise zero risk.** The monitor uses a [documented presence API](https://create.roblox.com/docs/cloud/reference/domains/presence), respects rate-limit responses, and only reads status. It does not launch games, automate gameplay, send Roblox messages, or bypass privacy settings. Those design choices do not make it Roblox-approved.

Roblox's [current terms](https://en.help.roblox.com/hc/en-us/article_attachments/54069120817172) require documented API access and allow suspension of API access for violations. Its [third-party app policy](https://en.help.roblox.com/hc/en-us/articles/37924211313044-Creator-Third-Party-App-Policy) restricts user tracking and sharing identifying information; it describes an exception for consent through official user, privacy, or parental settings where appropriate. Being connected or seeing a status manually does not establish blanket approval for this app. Use it only with appropriate consent and visibility provided by Roblox's settings. If you need an authoritative answer for your particular use, ask [Roblox Support](https://www.roblox.com/support) before connecting your account.

These sources were checked on **15 October 2026**. The linked terms PDF took effect on 19 May 2026; a terms page announcing a future 1 November update is not the current policy on that check date. Recheck policies before use.

## Can I play while the monitor is running?

**It should not create a second gameplay session.** Roblox says [error 264](https://en.help.roblox.com/hc/en-us/articles/36665660855700-Error-Code-264-Same-account-launched-experience-from-different-devices) concerns the same account accessing a game from multiple devices simultaneously. This program only makes web API requests and never launches an experience. That is an inference from its behavior and Roblox's explanation, not a Roblox guarantee about this program.

You can open Roblox and join a connection normally. Logging out, invalidating sessions, account security checks, or credential rotation can interrupt the monitor. Test it from the intended server while you play before relying on it. If Roblox rejects the server's session, keep its security protections enabled and resolve the rejection through supported Roblox tools.

## Before you start

You need:

- An always-on Linux computer with internet access and Python **3.11 or newer**, including `ssl`, `sqlite3`, and `fcntl`. No extra Python packages are used.
- Permission to administer that computer. Continuous service installation below uses **systemd 250 or newer**. Debian and Ubuntu commonly use systemd; other distributions may also use it. [OpenRC and other supervisor options](docs/DEPLOYMENT.md) are available separately.
- Your own Roblox account and a consenting connection whose online status your account can see.
- An Android phone with the free **ntfy** notification app. The free hosted service needs no paid plan or account for this walkthrough; [usage limits apply](https://docs.ntfy.sh/terms/).
- A desktop web browser for this version's session-cookie setup, initially and when a replacement session is needed. This is a current setup limitation, not a requirement to keep a workstation running. No browser is installed on the server by these instructions.

The initial account session and real phone delivery have to be tested for each installation. Automated tests cannot prove either one works.

## Beginner walkthrough

### If you mainly use a phone and someone is handling the server

The terminal instructions below are for the person administering the server. You do not have to type them yourself if a trusted administrator or assistant already has authorized server access. They can prepare configuration, run checks, and install/start only this monitor after the live acceptance checks pass.

Your phone tasks are to install ntfy, add the exact private topic prepared for your installation, allow background delivery, and confirm that test notifications arrive. The project name is not the topic: do not invent a topic name such as `Roblox-Presence`. The phone and server must use the same randomly generated string. Obtain it from the protected setup file or the operator's `subscription` command; keep it out of public documentation and screenshots.

On ntfy's **Subscribe to topic** screen, paste that exact string into **Topic name**, leave **Use another server** unchecked for the default `ntfy.sh` setup, check **Instant delivery in doze mode**, and tap **SUBSCRIBE**. If the main screen warns about battery optimization, tap **FIX NOW** and allow the background/battery exemption requested by Android. The [official phone guide](https://docs.ntfy.sh/subscribe/phone/) explains delivery options.

The authenticated monitor still needs your own Roblox session. Installing ntfy does not connect your Roblox account. The current secure prompt is described in step 5; ordinary mobile browsers do not provide the desktop developer-tools workflow described there. A server administrator can handle deployment but cannot authorize Roblox as you or obtain your account session without your participation. Do not send credentials through chat as a shortcut. A successful public API reply saying `offline` is not evidence that monitoring without an account login will work; compare during a known online session before choosing another authentication approach.

### If you are administering the server yourself

Follow the steps in order. Each step says which device to use. A **terminal** is an app where you type commands and press Enter. On a Linux workstation, search your application menu for “Terminal.” In many terminals, **Ctrl+Shift+V** pastes. Copy one command at a time. Text shown as an expected result is not a command.

Words in CAPITALS such as `SERVER_ADDRESS` are placeholders: replace them with your own information. Do not paste placeholders unchanged. If a command reports an error, stop at that step and use the troubleshooting table below.

### 1. Install the phone app — on your phone

Install [ntfy from Google Play](https://play.google.com/store/apps/details?id=io.heckel.ntfy). Open it and allow notifications when Android asks. You do not need a paid subscription. Keep the app available; you will add the notification topic in step 6.

### 2. Connect to the always-on computer — using your existing SSH access

If you already have a working SSH connection from a workstation or phone terminal app, use that same connection. SSH lets that device type commands on the server. For a typical setup, replace `SERVER_USERNAME` and `SERVER_ADDRESS` in:

```bash
ssh SERVER_USERNAME@SERVER_ADDRESS
```

If your administrator gave you a key or a saved SSH host name, use their existing connection instructions instead. Do not change SSH or firewall settings for this project. Passwords typed at an SSH prompt may show no characters; that is normal. Verify any new host-key fingerprint through your trusted administration records before accepting it.

**Checkpoint:** you are connected to the always-on computer. All commands in steps 3–9 run in this SSH terminal, even though you are typing on your workstation. Do not run the continuous monitor on a workstation that is usually off.

### 3. Get the project and check the computer — in the server terminal

Use a new directory dedicated to this project. For a fresh setup:

```bash
mkdir -p "$HOME/projects"
cd "$HOME/projects"
git clone https://github.com/adlererik/Roblox-Presence.git
cd Roblox-Presence
python3 --version
python3 deploy/preflight.py
python3 -m unittest discover -v
```

If a copy has already been prepared for you on the server, `cd` to that copy instead of cloning another one. A private repository requires GitHub access; use your established GitHub authentication or transfer a downloaded source archive over SSH. Your GitHub password is not a Roblox credential.

**Checkpoint:** Python reports at least 3.11, preflight reports `"supported": true`, and tests finish with `OK`. For the service instructions in step 9, preflight must also report `"systemd_install_supported": true`. Keep preflight output private because it contains host and service inventory.

If Git/Python is missing, or systemd is unsupported, have the computer's administrator provide the prerequisites or use [another deployment option](docs/DEPLOYMENT.md). This guide does not update a production server or install system packages.

### 4. Identify the two Roblox accounts — in the server terminal

Use each account's **username**, not its display name. The username is the name after `@` on its Roblox profile. Omit the `@` in the commands:

```bash
python3 -m roblox_presence resolve YOUR_USERNAME
python3 -m roblox_presence resolve CONNECTION_USERNAME
```

Each command prints a result like `{"user_id": 123456789}`. Write down the number for your account and the number for your connection. Numbers are public identifiers, not passwords.

Put those two numbers in this next command:

```bash
python3 -m roblox_presence init --directory .local --observer-id YOUR_ACCOUNT_NUMBER --target-id CONNECTION_ACCOUNT_NUMBER --without-cookie
```

Here, **observer** means your account; **target** means the connection you want a notification about. `.local` is this program's private setup folder. The command creates your configuration and a long random notification topic; you do not have to edit a configuration file manually.

**Checkpoint:** it says `Created protected local setup`. If it says `Local setup already exists`, keep the existing setup and continue only if it has the correct accounts. Do not delete it or generate a replacement topic just to repeat this step.

### 5. Connect your own Roblox session — browser on your workstation, prompt on the server

**Read this first:** this version uses your `.ROBLOSECURITY` session cookie, which can grant account access. It is not a limited “online status only” key. [Roblox warns never to share cookies](https://en.help.roblox.com/hc/en-us/articles/203313380-Keep-Your-Account-Safe). Keep it entirely on computers you control and trust. Never send it to a chatbot, another person, GitHub, ntfy, a screenshot, or a cookie-copying website/extension. If you do not want a full account credential on the server, do not use this version's authenticated setup.

The program sends this credential only to its fixed Roblox HTTPS endpoints. It stores the value in a protected file, excluded from Git and release archives. Anyone who controls your server or your user account may still be able to read it. No credential from the connection being monitored is required.

First, in the **server terminal**, run:

```bash
python3 -m roblox_presence --config .local/config.json set-cookie
```

Leave the terminal at the hidden input prompt. Then, on your **workstation**:

1. Open `https://www.roblox.com` in a desktop browser and log in to **your own account** normally. Check the username. Leave account security protections enabled.
2. Open the browser's developer tools, usually with **F12** or **Ctrl+Shift+I**. On some laptops, F12 requires the Fn key.
3. In **Firefox**, select **Storage**, then expand **Cookies** and select the Roblox site. In **Chrome/Chromium/Edge**, select **Application**, then **Storage → Cookies**, and select the Roblox site. A hidden tab may be under a `»` menu. These are built-in browser tools; no extension or console script is needed. See [Firefox's guide](https://firefox-source-docs.mozilla.org/devtools-user/storage_inspector/index.html) or [Chrome's guide](https://developer.chrome.com/docs/devtools/application/cookies).
4. Find the row named **`.ROBLOSECURITY`**. Copy its complete **Value**, including any warning text that is part of that value. Copy only the value, without the name, `=`, quotation marks, or other cookie rows. Do not change or delete the browser cookie.
5. Return to the server terminal's hidden prompt, paste the value, and press Enter. No characters should appear while pasting. Never put it after a shell command.
6. It should say `Cookie saved without displaying it.` Close developer tools and replace your clipboard contents with harmless text. Clear saved clipboard history containing the value if your desktop keeps one.

Logging out of that browser session may invalidate the saved credential. There is no guarantee a session stays valid indefinitely or works from a different network. The next step checks the actual server access. Do not disable session protection if it fails.

### 6. Add your private notification topic — terminal and phone

In the server terminal:

```bash
python3 -m roblox_presence --config .local/config.json subscription
```

It prints an address beginning `https://ntfy.sh/rp-`, followed by a long random string. **Keep that entire address private.** Anyone with it can read or publish to the topic on the free service. It is a secret address, not a password-protected channel, and the hosted provider processes/caches the messages.

On your phone, open ntfy, tap **+ / Subscribe**, and add a subscription:

- **Server:** `https://ntfy.sh` (normally the default).
- **Topic:** everything after the final `/` in the printed address, starting with `rp-`. Copy it exactly; do not use a short guessable topic such as `roblox`.

For prompt Android delivery, enable **Instant delivery** for the subscription if that option is offered. Allow background operation in Android's app settings and enable ntfy's **High** notification channel. Check sound/vibration and Do Not Disturb settings. Menu names vary by device/app version; follow the [official ntfy Android guide](https://docs.ntfy.sh/subscribe/phone/) if yours differs. The F-Droid build uses instant delivery automatically.

Notifications contain generic status text and an observation time. They contain no Roblox account names, IDs, game locations, or session credentials. Online notifications link to Roblox's home page; open the connection in Roblox yourself. You can use an authenticated self-hosted ntfy server separately if you need access controls.

### 7. Test the phone and real account visibility — in the server terminal

Send a test:

```bash
python3 -m roblox_presence --config .local/config.json test-push
```

**Checkpoint:** your phone receives “Roblox monitor test.” The terminal's `Provider accepted the test` only confirms ntfy accepted it. Confirm it appeared promptly on the actual phone. Repeat with the phone locked and idle for several minutes, first on Wi-Fi and then on mobile data. An unlocked-phone test alone is insufficient.

When your connection is **known to be online** and you can see that in Roblox, run:

```bash
python3 -m roblox_presence --config .local/config.json check
```

**Checkpoint:** the result includes `"observer_verified": true`, `"target_verified": true`, and `"visible_status": "online"`. An `offline` result while the person really is online means this installation has not passed the visibility check. A valid offline reply cannot distinguish being offline from privacy-filtered visibility. Do not assume parental/account linking guarantees this API view, and do not bypass their settings.

### 8. Try one real online notification — in the server terminal

Start a temporary trial:

```bash
python3 -m roblox_presence --config .local/config.json run
```

Leave this terminal open for the trial. The program keeps running, so the terminal does not return to its normal prompt. If the connection is already online, the default is to send one initial notification. Otherwise, arrange a normal offline-to-online transition. Allow at least two successful offline polls before the next online test. Check that the phone receives one online alert, then open Roblox and join them as you normally would.

While you play, use a **second SSH terminal**, `cd` to the same project directory, and run:

```bash
python3 -m roblox_presence --config .local/config.json status
```

After the monitor has completed a few polls, `"healthy": true` confirms recent checks and a working delivery worker. A second `check` can confirm account access while you play. This tests your actual session behavior; it is not a promise about future Roblox changes.

**Stop the trial with Ctrl+C in its original terminal** before installing the service. A foreground trial stops when its terminal closes; it does not yet provide continuous operation.

### 9. Install continuous operation — in the server terminal, systemd hosts only

Proceed after the real visibility and phone checks pass. Keep the terminal in the project directory. First preview the installation:

```bash
python3 deploy/install.py --config "$PWD/.local/config.json"
```

This first command writes nothing. It should show only these reserved paths: `/opt/roblox-presence`, `/etc/roblox-presence`, and `/etc/systemd/system/roblox-presence.service`, with `"apply": false` and `"service_started": false`. If those paths already exist, the first-install helper refuses to overwrite them. Have the administrator inspect an existing installation instead of deleting it.

Copy the monitor's files into those paths, verify its unit, then start **only this monitor**. Run each command separately and check for errors before the next:

```bash
sudo python3 deploy/install.py --config "$PWD/.local/config.json" --apply
sudo systemd-analyze verify /etc/systemd/system/roblox-presence.service
sudo systemctl daemon-reload
sudo systemctl enable --now roblox-presence.service
sudo systemctl status roblox-presence.service --no-pager
```

`sudo` may ask for your server account's administration password; it does not ask for a Roblox password. The installer copies credentials into root-only files and leaves the unit disabled. `enable --now` starts the monitor and arranges startup when this server boots. `daemon-reload` makes systemd read unit files; it does not restart production applications. These instructions require no firewall changes, reverse proxy changes, server reboot, or restart of unrelated services.

**Checkpoint:** status shows **`active (running)`**. Wait about a minute, then check the installed service's health:

```bash
cd /opt/roblox-presence/current
sudo python3 -B -m roblox_presence --config /etc/roblox-presence/config.json status
```

Expect `"healthy": true`. The service has its own persistent state directory, so a connection already online may generate one initial alert when moving from the trial to the service.

Now repeat a real phone/online transition check with the service running. Check health again later to establish that it remains working. You may close SSH and turn off the workstation after this passes. **The always-on computer must stay powered on and connected to the internet.** Do not reboot a production server just to test startup.

### 10. Check or stop it later — connect to the server again

Service status and recent logs:

```bash
sudo systemctl status roblox-presence.service --no-pager
sudo journalctl -u roblox-presence.service -n 50 --no-pager
```

Stop it and disable automatic startup:

```bash
sudo systemctl disable --now roblox-presence.service
```

Start it again:

```bash
sudo systemctl enable --now roblox-presence.service
```

These commands affect this monitor only. They retain its credentials and state. Do not delete state files to resolve a login problem; the saved state prevents repeated alerts.

## Troubleshooting

| What you see | What to do |
| --- | --- |
| `git: command not found`, old Python, or preflight unsupported | Ask the host administrator to provide prerequisites. Use the appropriate supervisor guide; do not run a broad server upgrade as a workaround. |
| GitHub says repository not found or asks for authentication | Confirm the repository URL and access. A private repository needs your existing GitHub credentials, or an archive transferred over SSH. Never use a Roblox credential here. |
| `No module named roblox_presence` | You are in the wrong directory. `cd` to the source project, or `/opt/roblox-presence/current` for the installed service. |
| `Local setup already exists` | Keep the existing private setup. Do not repeat `init` or delete the topic. |
| `Cannot read a credential file` | Complete `set-cookie`; check the configured file paths and permissions. Do not print the secret to diagnose it. |
| `roblox_authentication_failed` | The server cannot use the saved session. Refresh only your own session through the secure prompt; keep Roblox security protections enabled. |
| `roblox_observer_mismatch` | The session belongs to another account. Sign in to the configured observer account and replace only its cookie. |
| `visible_status` says `offline` while the connection is online | Confirm the correct ID and official visibility settings together. Do not activate continuous monitoring until a known online check works. |
| The terminal accepts a test, but the phone stays silent | Check server/topic spelling, notification permission, High channel, Instant delivery/background settings, mute and Do Not Disturb. Repeat the locked/idle test. |
| A rate-limit error | The monitor backs off automatically. Do not speed up polling, rotate identities, or run parallel copies to evade limits. |
| `Reserved monitor paths already exist` / installation refused | This is a first-install tool. Inspect the existing installation or partial files before doing anything else; do not delete unrelated paths. |
| Service is running but `healthy` is false | Wait for the first checks, then read this unit's logs. Running alone does not mean Roblox access and push delivery work. |
| No outage notification arrives | If the server, network, or push provider is down, the monitor may be unable to send one. Check service health directly. |

### Replace an expired cookie after systemd installation

In the **server terminal**, return to the original setup directory (for the fresh-clone walkthrough, `cd "$HOME/projects/Roblox-Presence"`). Keep the `.local` setup so you can use its hidden prompt again:

```bash
python3 -m roblox_presence --config .local/config.json set-cookie
python3 -m roblox_presence --config .local/config.json check
sudo install -m 600 -o root -g root .local/roblox_cookie /etc/roblox-presence/roblox_cookie
sudo systemctl restart roblox-presence.service
```

Use step 5 to obtain your own fresh session. Continue to the copy/restart commands only after the check succeeds. Restarting this unit refreshes its systemd credential snapshot; merely updating the file does not. Recheck installed health. Keep the topic and database unchanged. If a cookie was exposed, first revoke that session using Roblox's account security controls.

## Behavior and limits

- The default poll interval is 15 seconds. Detection depends on when Roblox reports the change, request time, and phone delivery; immediate notification is not guaranteed. Very brief transitions or transitions during outages can be missed.
- Online, in-game, and in-studio count as online. One alert is sent per observed online session. Two consecutive valid offline results rearm it; switching games while online does not trigger another alert.
- Failed checks, expired sessions, missing results, and unknown status types are never treated as offline. Source failures lasting five minutes generate an outage alert when delivery is possible, followed by a recovery alert.
- SQLite preserves transitions and pending notifications across restarts. Delivery retries run separately, honor backoff, pause when observations are stale/failing, and expire undelivered online alerts after five minutes. A crash after provider acceptance but before saving the acknowledgement can cause a duplicate.
- This is a status notifier. It does not record game locations, experience history, messages, or a connections list. Protected local state contains account IDs, the latest observed state/check times, and a bounded notification outbox. Hosted push services receive generic messages and timing; they do not receive the monitored account's identifier or cookie.

See [deployment options](docs/DEPLOYMENT.md), [design](docs/DESIGN.md), [verification](docs/VERIFICATION.md), and [primary sources](docs/SOURCES.md). Keep personal account names, device/host details, inventory, credentials, and logs in ignored private files rather than published examples. Systemd deployment has been tested on Linux; the OpenRC example has syntax checks but has not been tested on a live OpenRC host.
