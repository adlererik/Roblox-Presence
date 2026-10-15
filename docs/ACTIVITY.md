# Your activity graph and command guide

The monitor has to run on your always-on server. Your phone or computer opens a
report file when you want to look at it. Turning off the viewing device does not
stop the server recording new activity.

## Generate and view from your phone

Version **0.3.0** adds a persistent private dashboard. Follow the
[one-time dashboard setup](DASHBOARD.md), then bookmark the secret URL it prints.
Open that bookmark on your phone or computer and tap **Generate new graph**.
The page refreshes while generating and displays the new fourteen-day graph.
No SSH, terminal, sudo, app installation or running workstation is needed for
this everyday action. Your server and monitor must still be running and reachable
on your trusted private network or existing VPN/SSH connection.

The **same URL** always opens the latest saved graph. Generating replaces that
snapshot. Closing a browser/terminal and restarting the monitor do not remove it.
Reload an already-open tab to see a graph generated on another device. Keep the
URL private: it grants viewing and generation, and does not expire automatically.
HTTP is not encryption; do not expose its port or URL publicly.

## Everyday commands without sudo

Run these as the regular account selected during dashboard setup:

```bash
robox graph
robox dashboard
robox status
robox --help
```

`graph` starts generating and returns the bookmarked URL; open it to see progress.
`dashboard` prints the same URL without generating. `status` shows current health
through the private command API. These commands do not read the Roblox cookie,
root configuration or SQLite state. Their protected client settings live in
`~/.config/roblox-presence/dashboard.json` and contain only the private URL.

To download a fresh self-contained HTML copy into your home folder:

```bash
robox graph --file-only
robox graph --output "$HOME/activity.html"
```

The printed file URL works on the computer holding the file. Use the persistent
HTTP dashboard URL on your phone, or download the HTML using **Download saved
graph** on the page. Downloaded copies remain until you delete them.

### Without a persistent dashboard

An explicit private monitor config still supports the older temporary viewer:

```bash
sudo robox --config /etc/roblox-presence/config.json graph --listen SERVER_PRIVATE_ADDRESS
```

Replace the CAPITALS with this server's private numeric IP. This legacy mode
needs state access, keeps its terminal open and expires after ten minutes.
`--minutes 30` allows up to sixty minutes; `--port` selects a free unprivileged
port; defaults bind loopback or the config's saved address. It never changes a
firewall or proxy. The persistent dashboard needs none of those temporary options.

For a loopback listener with existing SSH forwarding, forward its printed port
from a second terminal on the viewing computer:

```bash
ssh -N -L LOCAL_PORT:127.0.0.1:REPORT_PORT SERVER_USERNAME@SERVER_ADDRESS
```

Replace every CAPITALIZED value. Open the printed URL using `LOCAL_PORT`, keeping
the secret path unchanged. Phone SSH clients use their local-forwarding feature.

## Save a file only, without a viewer

```bash
robox graph --file-only
```

The command prints the full filename and an **Open saved graph** `file://` link.
The URL escapes spaces and other filename characters. Click it in a supporting
terminal or paste it into a browser **on the computer holding the file**. A server
file URL refers to the server’s disk; it does not copy the report to your phone.

The default file is `roblox-presence.html` in your home folder, owned by you and
readable only by you. Run the command again to replace it with a fresh snapshot.
To choose another file in a folder you own:

```bash
robox graph --file-only --output "$HOME/activity.html"
```

To view a server file elsewhere, download it with your existing SSH/SFTP client,
then open the downloaded HTML in your browser. On a computer you can usually
double-click it in Downloads. On a phone, use your trusted server file-transfer
app and choose **Open with** your browser. A computer-terminal example, run on the
**viewing computer** outside the server SSH session, is:

```bash
scp SERVER_USERNAME@SERVER_ADDRESS:roblox-presence.html "$HOME/Downloads/roblox-presence.html"
```

Replace both CAPITALIZED words and use your existing SSH options/key if needed.
The downloaded report works offline. Keep it out of public hosting and GitHub;
it contains personal activity times. It has no cookie, notification topic, or
numeric account ID. Downloaded copies remain until you remove them.

If `robox` is outside your command search path, use
`sudo /opt/roblox-presence/current/robox graph`. Source and non-systemd setups can
use `./robox --config /absolute/path/private/config.json graph` from the source
folder as the account permitted to read state. Help needs no configuration or
administrator access.

## Read the graph

- **Green:** the connection was observed online. In-game and Studio count too.
- **Pale gray:** verified offline checks.
- **Diagonal stripes:** no reliable checks, an unconfirmed offline result, or
  time before this version started recording. They do not mean offline.
- **White:** time later today that has not happened yet.

Each row is a day; the newest day is at the top. The right-hand number is observed
online time for that day. The cards show observed online time, online appearances, and how much of the fourteen-day window has reliable checks. Missing
history lowers coverage rather than pretending those days were offline. The full day remains visible on a narrow phone; the exact clock times are listed below.

Tap a date to filter the list of detected login/logout times below. Tap **Show all
days** to reset. On a computer, hover over a colored section for its start and end.
The list shows full dates, hours, minutes and seconds, with timezone and UTC offset.
An offline row shows both the first offline check and its later confirmation.
“First seen online/offline” means recording began in that state; it is not proof
that a login/logout happened at that time.

**These are detected changes, not exact account login/logout records.** Roblox
provides current presence, and the default check interval is 15 seconds. Its own
reporting delays, request time, outages and rate limits can add uncertainty. A
brief session may happen entirely between checks. The graph does not reconstruct
activity during a gap or before recording started. Green time is an estimate
between reliable checks, not a measure of active keyboard/gameplay time.

All dates and clock times come from the **server’s configured local timezone**,
which is named at the top of the report. They remain the same when you view it
somewhere else. The application cannot locate a physical server automatically.
Ask the administrator to confirm its timezone if the displayed clock is wrong;
the program does not change server time. Clock-change days have a `*` and their
own axis. The event list distinguishes repeated hours with UTC offsets.

The report covers the last fourteen local calendar dates, including today. The
server keeps fifteen elapsed days of checks so the report still works around
midnight and daylight saving changes. Old checks are pruned automatically while
the monitor runs. Downloaded reports and upgrade backups remain until you delete
them; database retention does not remove your copies.

## Every program command

Both spellings work: `robox` and `roblox`.

```bash
robox --help
robox help
robox graph --help
robox --version
```

The first two show a short explanation of every command. `COMMAND --help` gives
its options. The table below uses the installed systemd version. Dashboard graph/status commands use the regular operator account. Installation and
credential administration remain protected; help never needs configuration.

| Command | What it does |
| --- | --- |
| `robox --help` or `robox help` | Show all program commands. |
| `robox --version` | Show the installed version. |
| `robox graph` | Generate a fresh snapshot and print the permanent private page URL; no sudo or open terminal. |
| `robox dashboard` | Print the bookmarked private page URL without replacing its graph. |
| `robox graph --file-only` | Download a fresh HTML copy and print its local file link. |
| `robox graph --output "$HOME/activity.html"` | Download a fresh HTML copy to your chosen private filename. |
| `robox status` | Show current monitor health through the private dashboard API. |
| `sudo robox validate` | Check configuration structure without testing credentials or the network. |
| `robox check` | Check current Roblox status and verify the observing account; use a protected direct-file setup config as explained below. |
| `robox test-push` | Send a phone test; use the protected direct-file setup config below. |
| `robox subscription` | Display your private ntfy address; use the direct-file setup config and keep its output secret. |
| `robox resolve USERNAME` | Find the numeric ID of a Roblox username; omit the `@`. No login/config needed. |
| `robox init --observer-id YOUR_ID --target-id CONNECTION_ID --without-cookie` | Create private first-time setup in `.local`. Replace both IDs. Do not repeat on an existing setup. |
| `robox set-cookie` | Enter your own session through a hidden prompt, with the direct-file setup config. |
| `robox run` | Run continuously in this terminal, using a direct-file setup. The installed service normally handles this; do not run a second copy. |

`check`, `test-push`, `subscription`, `set-cookie`, and a foreground `run` need a
configuration pointing to protected credential source files. An installed systemd
configuration uses `credential:` references available only inside that service.
For the setup made by the beginner guide, return to its source folder and use:

```bash
./robox --config "$PWD/.local/config.json" check
./robox --config "$PWD/.local/config.json" test-push
```

The standalone check is a diagnostic, not an extra background monitor. To replace
an installed session, follow the [credential refresh instructions](../README.md#replace-an-expired-cookie-after-systemd-installation).
Use `sudo systemctl status roblox-presence.service --no-pager` for service status,
`sudo systemctl stop roblox-presence.service` to stop it, and
`sudo systemctl start roblox-presence.service` to start it. These are service
manager commands; they are not hidden `robox` subcommands.

## Notifications with names and games

An online notification names the player using their Roblox display name and
`@username`. It includes their game when the authenticated presence reply shares
it, plus the server-local observation time. A game is not guessed when Roblox
withholds it. Profile lookup failures fall back to “Your Roblox connection”;
valid presence checks can still work while that optional name lookup is failing.

Someone often opens Roblox before choosing a game. The first message can say
“No game reported yet.” If a game name becomes visible later in the same online
session, there is **one follow-up** naming it. If the initial alert has not been
sent, it is enriched instead. Further game changes do not send more alerts.
Offline confirmation rearms the next session. The first-game rule and delivery
retries survive restarts.

Your notification provider receives these player/game names and times. Your
phone can display them on its lock screen. Use a private unpredictable topic,
authenticated topic, or trusted notification server as appropriate; keep exported
reports and operational files out of the public repository.

## Updating an existing systemd installation

Do this only if you already have this project installed under
`/opt/roblox-presence`, with `roblox-presence.service`. A new installation uses the
[beginner guide](GETTING_STARTED.md). A non-systemd administrator should stop only
this monitor through their supervisor, make a consistent private SQLite backup,
replace its source, and restart only this monitor as its dedicated runtime user.
Never run two workers on the same state or make private state world-readable.

On the server, obtain the new release in a **new source directory**, then run its
tests. For example, start in a new empty folder and use:

```bash
git clone --branch v0.3.0 --depth 1 https://github.com/adlererik/Roblox-Presence.git
cd Roblox-Presence
python3 -m unittest discover -v
sudo python3 deploy/upgrade.py
```

The last command is a dry run: it changes nothing. If it reports that the update
can be prepared, apply it:

```bash
sudo python3 deploy/upgrade.py --apply --dashboard --graph --graph-listen SERVER_PRIVATE_ADDRESS
```

Replace `SERVER_PRIVATE_ADDRESS` with the server’s own private numeric IP. The sudo caller becomes the regular operator; use `--dashboard-user SERVER_USERNAME` for a different existing non-root account. Port 8765 must be free, or choose another with `--dashboard-port`. Omit `--dashboard` to upgrade code without enabling the page.

This saves a private consistent database backup, preserves account credentials,
the topic and service configuration, installs the command shortcuts, and restarts
**only `roblox-presence.service`**. It checks fresh monitor health and compares
other running services’ process/start times. It does not install packages, reboot, or edit networking. Dashboard opt-in adds only
`roblox-presence.service.d/dashboard.conf` and reloads unit definitions before
starting this monitor. Expect `"healthy": true`, `"production_services_unchanged": true`,
and a private dashboard URL. Keep that URL secret and bookmark it. From now on:

```bash
robox --help
robox graph
robox dashboard
robox status
```

Version 0.2.0 introduced recording; 0.3.0 preserves that history. For a first
upgrade from 0.1.0, history starts afterwards and fills gradually; there is no
earlier log to import from 0.1.0. Keep real online visibility
and phone-delivery checks in your acceptance process. A passing offline check is
not proof of online visibility.

If the update reports a failure, keep its files and backup and have the
administrator inspect only this monitor. Do not rerun the first-install script,
delete state, or automatically restore an old database after notifications may
have been sent: that could erase history and replay old alerts. Backups are under
`/opt/roblox-presence/backups`, accessible only to root.
