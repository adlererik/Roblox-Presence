# Deployment options

The runtime requires Linux, Python 3.11+ with `ssl`, `sqlite3`, and `fcntl`, outbound HTTPS, and normal DNS resolution. Debian, Ubuntu, and Gentoo are examples of possible hosts; choose deployment by the host's service manager and available Python rather than its distribution name. No browser or third-party Python packages are required.

## Prepare and verify on the intended host

1. Clone or extract the source into a separate directory and run the tests.
2. Use `init` to create local configuration with your observer/connection IDs. Enter the observer's own session through `set-cookie`.
3. Run `check` during a known online session and compare the result with Roblox.
4. Configure the receiving device, run `test-push`, and confirm prompt receipt while locked/idle and on the networks you use.
5. Run `deploy/preflight.py` on the host to inspect runtime availability, service-manager capabilities, and installation-path collisions. Its inventory output is private operational data; do not publish it.

If transferring setup between hosts, update absolute credential and state paths for the destination. Keep credentials in protected files outside the source release. A session that works on one network may need to be revalidated from the deployment host.

The package allowlist excludes `.local/`, credentials, databases, Git metadata, and caches. Verify the accompanying SHA-256 checksum after transfer. Running tests from a staging directory does not install or activate a service.

## Systemd

The provided first-install helper targets **systemd 250+**. This is an optional deployment path, not a runtime dependency. It uses a restricted dynamic identity, systemd credentials, restart supervision, a watchdog, and resource limits.

Set `SETUP_CONFIG` to the full path of your tested local configuration and run from the source directory:

```bash
python3 deploy/install.py --config SETUP_CONFIG
sudo python3 deploy/install.py --config SETUP_CONFIG --apply
sudo systemd-analyze verify /etc/systemd/system/roblox-presence.service
```

The first command is a no-write dry run. Applying copies this monitor's files only and refuses existing reserved paths. It does not install packages, run a service manager, or start a service. Review its paths and credentials before applying. On a live host, preserve all existing applications and avoid changing their units, network settings, or reverse proxies.

Activate only this unit after the live checks pass:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now roblox-presence.service
sudo systemctl status roblox-presence.service --no-pager
sudo journalctl -u roblox-presence.service -n 50 --no-pager
```

Systemd manages code under `/opt/roblox-presence`, root-only credential sources under `/etc/roblox-presence`, and persistent state under `/var/lib/roblox-presence`. To inspect health:

```bash
cd /opt/roblox-presence/current
sudo python3 -B -m roblox_presence --config /etc/roblox-presence/config.json status
```

After securely replacing a credential source, restart only `roblox-presence.service`; a running systemd credential snapshot does not automatically refresh. Do not delete SQLite state to rotate a session. Disable this installation with `sudo systemctl disable --now roblox-presence.service`, retaining state and configuration for recovery.

## OpenRC

`deploy/roblox-presence.openrc` is an example for hosts using OpenRC and `supervise-daemon`, such as an OpenRC-based Gentoo installation. Do not use the systemd installer for this path.

Using your distribution's account-management tools, create a dedicated unprivileged `roblox-presence` service account. Stage read-only code at `/opt/roblox-presence/current`. Place `config.direct.example.json` as `/etc/roblox-presence/config.json`, replace its example IDs with your own, and supply the referenced observer cookie and ntfy topic. The configuration directory and state/log directories must be accessible to that service account with mode 0700; credential files must have mode 0600 or 0400. Never reuse or change an unrelated application's account.

The direct configuration uses protected file paths rather than systemd's `credential:` references. Set up `/var/lib/roblox-presence` and `/var/log/roblox-presence` for this service account. Review the Python executable and code paths in the script, and arrange rotation of this service's log through the host's normal logging setup.

Install only the reviewed script as `/etc/init.d/roblox-presence` with mode 0755, then use:

```bash
sudo rc-service roblox-presence start
sudo rc-service roblox-presence status
sudo rc-update add roblox-presence default
```

Stop/remove startup for this monitor only with `rc-service roblox-presence stop` and `rc-update del roblox-presence default`. The example has shell syntax and path checks; it has not been validated on a live OpenRC host. Validate supervision, shutdown, credential access, and recovery on your host before relying on it. See [OpenRC's supervisor guide](https://github.com/OpenRC/openrc/blob/master/supervise-daemon-guide.md).

## Foreground or another supervisor

The Python process stays in the foreground, so a different supervisor can manage it directly:

```bash
python3 -B -m roblox_presence --config /absolute/path/to/config.json run
```

Run it as an unprivileged account able to read only its protected credentials and write its own state directory. Use absolute paths in the configuration. Configure restart-on-failure and a stop timeout of at least 45 seconds. Send SIGTERM for graceful shutdown. Avoid running multiple workers with different state directories for the same subscription, since they would independently send alerts.

The runtime works without `NOTIFY_SOCKET`; systemd readiness/watchdog reporting becomes a no-op. Polling, durable outbox, worker-stall detection, and local health status still operate. Apply equivalent sandboxing and resource limits using the chosen supervisor's facilities where available.

## Diagnostics

`status` returns success only when presence, the delivery worker, and health output are recent, with no unresolved source/push error. An expired observer session produces `roblox_authentication_failed`; a session for the wrong account produces `roblox_observer_mismatch`. Rate limits back off automatically.

A topic rotation also requires updating the receiving device's subscription. Keep installation-specific hostnames, addresses, account identifiers, service inventory, and logs in private operator notes rather than the shared repository.
