# A bookmarked graph page, without everyday sudo

After one administrator setup, your phone or computer can generate and view the
graph in a browser. The same private URL shows the latest saved graph. Nothing
needs to remain running on a laptop or in an SSH terminal.

## On your phone or computer

1. Connect to your trusted home network or established private VPN/SSH connection.
2. Open the private URL printed during setup. Keep the entire address secret.
3. Save it as a browser bookmark. You may also add it to your home screen.
4. Tap **Generate new graph**. The page refreshes while the server prepares it.
5. Read the fourteen daily timelines. Tap a date to filter the recorded times
   underneath. They include dates, hours, minutes, seconds and the server timezone.
6. Close the browser whenever you like. Return to the same bookmark next time.

The saved snapshot remains until you generate another. New generation replaces
it at the **same URL**; old open tabs need a refresh to see the replacement.
The snapshot and key survive monitor restarts and upgrades. They depend on the
server retaining its private address, port and key, and being reachable/running.
Browser/downloaded copies may remain on your devices until you delete them.

**Generate new graph** reads checks already recorded by the monitor. It does not
force extra Roblox requests or change the polling interval. The normal interval
is fifteen seconds; outages and Roblox reporting can add delay. An offline time
is the first offline check, shown after consecutive checks confirm it. The list
also shows its later confirmation. First-seen states and unknown intervals stay
clearly marked. These are precise observation timestamps, not an exact Roblox
login/logout audit. Activity before recording cannot be recovered.

## Commands as your normal server user

After the setup selects your account, these commands need **no sudo**:

```bash
robox graph
robox dashboard
robox status
robox --help
```

`graph` starts a new snapshot and prints the bookmarked URL. `dashboard` prints
the same URL without changing the snapshot. `status` checks the monitor's current
health. Your account reads only its protected client file,
`~/.config/roblox-presence/dashboard.json`, which contains the dashboard URL.
It does not get permission to read the Roblox cookie, root config or database.
`roblox` is an equivalent spelling.

To save a fresh HTML copy on the computer running the command:

```bash
robox graph --file-only
robox graph --output "$HOME/activity.html"
```

Use **Download saved graph** on the page for a browser download. Local `file://`
links refer to the device holding the file; the HTTP dashboard URL is the one
to bookmark across devices. No phone SSH app is required for the web button.

## One-time setup: administrator only

New users first complete the [installation and account checks](GETTING_STARTED.md).
Existing installations can combine upgrade and dashboard setup in the
[upgrade guide](ACTIVITY.md#updating-an-existing-systemd-installation).

For an installed, running **0.3.1 or later** systemd monitor, enter its downloaded
source directory in the server terminal. Preview the dashboard setup:

```bash
sudo python3 deploy/dashboard_setup.py --listen SERVER_PRIVATE_ADDRESS
```

Replace the CAPITALS with the server's own private numeric IP. The sudo caller
becomes the dashboard operator. To select another existing regular account, add
`--user SERVER_USERNAME`. Choose a free fixed port with `--port` if 8765 is occupied.
Do not change or stop the application already using a port.

Expected: a no-write dry-run message. Apply the same choices:

```bash
sudo python3 deploy/dashboard_setup.py --listen SERVER_PRIVATE_ADDRESS --apply
```

Expected: dashboard enabled and a private URL to bookmark. This creates a root-only
random key, a private client file owned by the selected operator, and only this
monitor's `roblox-presence.service.d/dashboard.conf`. It backs up configuration,
reloads unit definitions, restarts **only this monitor**, checks dashboard/monitor
health and compares other running services' process/start times.

The existing bind-deny rule remains; the drop-in permits only the selected TCP
port/address family. The Python code accepts only a specific private/loopback IP.
The service remains an unprivileged DynamicUser with no capabilities, a five-percent
CPU quota and idle I/O scheduling. Dashboard opt-in sets its own memory limit to
256 MiB for a large fourteen-day report. One generation can run at a time, with
ten seconds between requests and a lower-priority, separate graph process capped at 128 MiB of address space, eight seconds of CPU (ten-second hard limit) and sixty seconds elapsed time.

No web/proxy/firewall/router configuration, other service unit, system package or
global sudo rule is changed. This does not grant passwordless administrator access.
Installation, upgrades and account credential renewal still need the administrator.
If setup fails, preserve the files and ask for inspection of this monitor; do not
rerun first installation or delete state.

## If 0.3.0 stopped while saving operator settings

Version 0.3.0 could reject a user-owned `.config` folder with mode 0775, even
though the monitor's own settings can remain private inside it. Version 0.3.1
accepts that shared parent without changing its permissions, creates only the
application's mode-0700 subfolder, and keeps the client file mode 0600.

Use the [guarded upgrade to the new release](ACTIVITY.md#updating-an-existing-systemd-installation)
from its newly downloaded source. It preserves the protected key left by the
previous preparation and accepts only an exact generated drop-in matching the
configured or requested address/port. Custom or conflicting files still require
inspection. Earlier prepared files remain available; do not delete the state,
key or old source to make a retry work. The first-install script is not a repair.

## Privacy and access

The URL's 256-bit random path grants both viewing and generation. It deliberately
does not expire. Anyone with the link **and network access** can use it. Keep it out
of screenshots, GitHub, shared bookmarks and public messages. HTTP does not encrypt
traffic: use a trusted private network or existing encrypted VPN/SSH connection,
and never expose/forward the port publicly. If your existing firewall blocks the
port, keep that firewall unchanged and use established SSH forwarding as described
in [the activity guide](ACTIVITY.md).

There is no file browser, arbitrary query, cookie endpoint, account-control route
or request log. The API exposes only generation, the saved report and selected
health fields. Graph generation requires a same-origin form and a separate CSRF
nonce. Responses prohibit caching, referrers and framing. The HTML uses no external
scripts, fonts or tracking. The URL is absent from the downloaded HTML.

The administrator can revoke a leaked link by replacing only the protected
dashboard key, restarting this monitor, and reinstalling the operator's client
settings with the setup helper. Keep the key and client file private. Never change
database ownership/permissions to make graph commands work.

## Other Linux supervisors

The runtime is independent of Linux distribution. The automatic helper above
targets the existing systemd installation. An OpenRC/other-supervisor administrator
can add this optional object to the dedicated monitor's protected config:

```json
"graph_listen_address": "SERVER_PRIVATE_ADDRESS",
"dashboard": {
  "port": 8765,
  "key_file": "/absolute/private/path/dashboard_key"
}
```

Create that key as 64 random hexadecimal characters (for example with
`python3 -c 'import secrets; print(secrets.token_hex(32))'`), accessible only to the
runtime account, and supervise the existing monitor as that non-root account.
Give each authorized operator a mode-0600 client JSON containing only
`{"url": "http://SERVER_PRIVATE_ADDRESS:8765/SECRET_KEY/"}`. Replace every
placeholder. Apply equivalent bind/resource/credential isolation through your
existing supervisor; do not run another monitor on the same state. Live OpenRC
dashboard activation has not been validated. The browser interface is the same.
