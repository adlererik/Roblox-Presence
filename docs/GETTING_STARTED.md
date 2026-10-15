# Install on your own server

Roblox Presence Monitor sends a phone notification when a consenting Roblox connection appears online. It can help friends, relatives, or teammates find a time to play together without repeatedly opening Roblox to check. You open Roblox and join them yourself after the alert.

Your always-on Linux server checks Roblox, normally about every 15 seconds. It sends a message with the player’s name and any visible game through ntfy, which delivers it to your phone. Your laptop does not have to stay on. A phone notification depends on Roblox's reporting, your server's internet connection, and your phone's delivery settings; it is not an instant-delivery guarantee.

## What you need

- A Linux server that stays on, internet access, and permission to administer it. The runtime needs Python 3.11 or newer with its standard `ssl`, `sqlite3`, and `fcntl` modules. No extra Python packages are required.
- A way to connect to that server, usually SSH. Ask your server administrator for your own login name and server address if you do not know them. Never post passwords or keys in an issue.
- Your own Roblox account and a consenting connection whose online status your account can see.
- The ntfy app on your phone, from the [official Android or iOS download links](https://docs.ntfy.sh/subscribe/phone/). This guide uses the free `ntfy.sh` service; no paid account is required, and [service limits apply](https://docs.ntfy.sh/terms/).
- A way to authorize your own Roblox session. The manual route uses a desktop browser once. A phone-only route is available with an administrator's help through [Quick Sign In](../README.md#optional-phone-authorization-with-quick-sign-in).

The automatic service installation below needs **systemd 250 or newer**. Choose by your server's software, not its brand or distribution. On OpenRC or another service manager, use the [separate deployment guide](DEPLOYMENT.md#openrc); its OpenRC example needs administrator review and has not been verified on a live OpenRC installation. This release does not claim support for every server operating system.

**Account access:** this version stores a full session credential for your own Roblox account. It is not a limited permission to read status. Keep account protections enabled. Never give the monitored person’s password to this program, and never post any session cookie, private topic, or private configuration. Read [account risk and credential handling](../README.md#can-this-get-my-roblox-account-banned) before connecting your account.

## 1. Open a terminal and connect to your server

A terminal is where you type commands and press Enter. Use your established SSH app or terminal. Replace the words in capitals with your own information:

```bash
ssh SERVER_USERNAME@SERVER_ADDRESS
```

If your existing SSH setup uses a key or saved host name, use that setup. Do not alter SSH, firewall, or router settings for this monitor. Check a new host fingerprint through your administrator's trusted records.

**From now on, terminal commands run on the server.** You are using your laptop or phone only to control it.

## 2. Download the release and check the server

Copy one command at a time:

```bash
mkdir -p "$HOME/projects"
cd "$HOME/projects"
git clone --branch v0.3.0 --depth 1 https://github.com/adlererik/Roblox-Presence.git
cd Roblox-Presence
python3 --version
python3 deploy/preflight.py
python3 -m unittest discover -v
```

Git's "detached HEAD" message is normal when selecting a release tag. It does not prevent installation.

**Expected:** Python is at least 3.11, preflight includes `"supported": true`, and tests finish with `OK`. For step 8, preflight must also include `"systemd_install_supported": true`. Keep preflight output private because it includes server inventory. If prerequisites are missing, ask the administrator to provide them; do not upgrade a production server as a workaround.

If the project directory already exists, inspect that copy instead of repeating the clone. As an alternative, the release page has `roblox-presence-0.3.0.tar.gz` and its `.sha256` file. Download both onto the server, run `sha256sum -c roblox-presence-0.3.0.tar.gz.sha256`, extract the archive with `tar -xzf roblox-presence-0.3.0.tar.gz`, and enter the extracted `roblox-presence` directory.

## 3. Choose the two Roblox accounts

Use the username after `@` on each Roblox profile, without typing the `@`. A display name can be shared by several people and is not the same thing.

```bash
python3 -m roblox_presence resolve YOUR_USERNAME
python3 -m roblox_presence resolve CONNECTION_USERNAME
```

Each prints a `user_id` number. Write down which number belongs to which account. Use those numbers here:

```bash
python3 -m roblox_presence init --directory .local --observer-id YOUR_ACCOUNT_NUMBER --target-id CONNECTION_ACCOUNT_NUMBER --without-cookie
```

**Expected:** `Created protected local setup`. "Observer" means your account. "Target" means the connection you want a notification about. The private `.local` folder holds your settings and a newly generated random notification address. Do not publish this folder or repeat initialization over an existing setup.

## 4. Connect your own Roblox session

Follow the [browser and hidden terminal prompt instructions](../README.md#5-connect-your-own-roblox-session--browser-on-your-workstation-prompt-on-the-server). They explain exactly where to find your own session value and how to paste it into the server prompt without displaying it. Do not put the value after a shell command or send it through chat.

If you only use a phone, have your administrator follow [Quick Sign In](../README.md#optional-phone-authorization-with-quick-sign-in). The temporary browser runs on the server and presents a short-lived code. Approve it in your own Roblox app under **More → Quick Sign In**, after reviewing the device and full-account access. The helper needs separate browser prerequisites and verifies the resulting account before saving anything. It stops when its code expires. This feature is not available to every account.

Installing ntfy alone does not connect your Roblox account. Logging out or revoking a session can invalidate the server's credential later; that calls for a new authorization, not disabling security protections.

## 5. Connect ntfy to the server's private topic

In the server terminal:

```bash
python3 -m roblox_presence --config .local/config.json subscription
```

It displays a private address beginning `https://ntfy.sh/rp-`. Keep the whole address private: anyone with it can read or publish to that unprotected topic.

On your phone, open ntfy, allow notifications, and add a subscription. Use `https://ntfy.sh` as the server and copy everything after the last `/` into the topic field. Do not replace the random string with the project name. Your phone and server need the exact same topic.

On Android, enable Instant delivery if offered, allow background operation, and check that the High notification channel has sound enabled. Other clients have different menus; follow [ntfy's phone instructions](https://docs.ntfy.sh/subscribe/phone/). Device names, brands, and personal account details are not part of this project's defaults.

## 6. Check phone delivery and real Roblox visibility

```bash
python3 -m roblox_presence --config .local/config.json test-push
```

**Expected:** "Roblox monitor test" appears on your phone. "Provider accepted" in the terminal alone is insufficient. Repeat with your phone locked and idle for several minutes, on Wi-Fi and mobile data, and check the sound you want.

When your connection is known to be online and you can see that in Roblox, run:

```bash
python3 -m roblox_presence --config .local/config.json check
```

**Expected:** `"observer_verified": true`, `"target_verified": true`, and `"visible_status": "online"`. An offline reply alone does not prove this API can see the connection. If the app says online but this says offline, check the accounts and official visibility settings together. Do not bypass privacy settings or assume an account relationship guarantees API visibility.

## 7. Try an actual online alert

```bash
python3 -m roblox_presence --config .local/config.json run
```

Leave this terminal open for the trial. The command keeps running and does not return to its prompt. Arrange a normal offline-to-online transition and confirm one phone alert. If the connection is already online, the default is one initial alert. Two successful offline polls rearm the next alert; the first visible game can produce one follow-up if the initial alert had no game. Later game switches do not send more alerts.

Open Roblox and join the connection normally. In a second SSH terminal, enter the project directory and run `python3 -m roblox_presence --config .local/config.json status` to check that monitoring remains healthy while you play. After the trial, press **Ctrl+C** in its original terminal to stop it. This temporary trial does not yet survive closing the terminal.

## 8. Install automatic operation on a systemd server

Proceed after the real visibility and phone checks pass. Stay in the source directory, with the temporary trial stopped. Preview first:

```bash
python3 deploy/install.py --config "$PWD/.local/config.json"
```

**Expected:** `"apply": false` and `"service_started": false`, with only dedicated monitor paths under `/opt/roblox-presence`, `/etc/roblox-presence`, and `/etc/systemd/system/roblox-presence.service`. If reserved paths already exist, stop and have the administrator inspect them. This is a first-install tool, not an upgrade command.

Run these separately, checking each for errors:

```bash
sudo python3 deploy/install.py --config "$PWD/.local/config.json" --apply
sudo systemd-analyze verify /etc/systemd/system/roblox-presence.service
sudo systemctl daemon-reload
sudo systemctl enable --now roblox-presence.service
sudo systemctl status roblox-presence.service --no-pager
```

`sudo` may ask for your server's administrator password. Enter it in the terminal, never in an issue or chat. The installer copies only this monitor's code and protected credentials. Starting this unit does not require restarting other applications, changing a reverse proxy, opening a port, or rebooting the server.

**Expected:** `active (running)`. After about a minute, check actual health:

```bash
cd /opt/roblox-presence/current
sudo python3 -B -m roblox_presence --config /etc/roblox-presence/config.json status
```

**Expected:** `"healthy": true`. Running alone is not proof of working account access. If health is unavailable immediately after startup, allow the first checks to finish and repeat the health command; do not repeat installation over the existing files.

The server now owns continuous operation and starts the monitor at boot. Your laptop and SSH session can close. Roblox session expiry, outages, visibility changes, and phone delivery settings can still interrupt alerts. Keep the private setup files for [secure credential renewal](../README.md#replace-an-expired-cookie-after-systemd-installation).

## 9. Enable your bookmarked private graph page

This is a one-time administrator step. From the downloaded source directory on
this server, replace `SERVER_PRIVATE_ADDRESS` with its own private numeric IP:

```bash
sudo python3 deploy/dashboard_setup.py --listen SERVER_PRIVATE_ADDRESS
sudo python3 deploy/dashboard_setup.py --listen SERVER_PRIVATE_ADDRESS --apply
```

The first command previews without writing. The second backs up configuration,
sets up only this monitor's dashboard, restarts only this monitor, and prints a
private URL. The sudo caller becomes the regular operator. If port 8765 is already
in use, add `--port ANOTHER_FREE_PORT` to both commands; do not stop the existing app.

**On your phone:** open that URL while on your trusted home network or existing
private VPN/SSH connection. Bookmark it. Tap **Generate new graph**. The page shows
generation progress, then the graph. Tap dates to see recorded online/offline times
with seconds. Close your browser when finished; return to the same bookmark later.

The URL and latest saved graph do not expire. Generating another graph replaces
the snapshot at that same address. No open SSH terminal or laptop is needed.
Keep the URL secret: anyone with it and network access can view/generate.
HTTP does not encrypt traffic; never expose the port publicly. Existing firewall,
proxy and website settings are preserved.

The selected regular account can now run `robox graph`, `robox dashboard`,
`robox status` and `robox --help` **without sudo**. No access to the Roblox cookie
or private database is granted. [The dashboard guide](DASHBOARD.md) explains
port choices, SSH forwarding, other supervisors and the protected client file.

## Stop or troubleshoot

To stop only this monitor and turn off its automatic startup:

```bash
sudo systemctl disable --now roblox-presence.service
```

Keep credentials and saved state unless you are deliberately removing the installation; deleting state can cause repeated alerts. For errors, use the [troubleshooting table](../README.md#troubleshooting). When asking for help, share the safe error code and software versions, not raw configuration, health files, logs, cookies, private topics, screenshots containing secrets, or server inventory.
