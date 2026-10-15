# Roblox Presence Monitor 0.2.1 — clickable graph links

Generate the fourteen-day activity graph on your always-on server, then open it
in a phone or computer browser using the link printed in your terminal.

- **Clickable browser link:** `sudo robox graph` saves the private HTML snapshot
  and starts a temporary viewer. Click the printed URL. Keep the terminal open;
  the link closes after ten minutes or Ctrl+C. The monitor keeps running.
- **Phone and computer:** select the server's specific private IP with
  `--listen SERVER_PRIVATE_ADDRESS`, or save it during setup/upgrade for next time.
  Both devices need trusted home-network access or an existing private VPN/SSH
  connection. Loopback remains the default when no address is selected.
- **File-only option:** `sudo robox graph --file-only` prints an escaped `file://`
  URL without starting a viewer. That URL works on the computer holding the file;
  download a server file before opening it on another device.
- **Limited viewer:** a fresh random secret path serves just one in-memory report.
  No directory browsing, credentials, write operations or access logs. Root graph
  commands drop to the original sudo caller before listening. Links expire, slow
  requests are bounded, and responses prohibit caching, referrers and framing.
- **Guarded update:** existing activity, credentials and notification state are
  preserved. An optional saved viewing address is backed up and updated atomically.
  Only the monitor's service is restarted; no networking or other service is changed.

Follow the [beginner installation guide](GETTING_STARTED.md) for a new server or
the [upgrade guide](ACTIVITY.md#updating-an-existing-systemd-installation) for an
existing systemd installation. The [activity guide](ACTIVITY.md) explains browser
links, saved files, SSH forwarding, timezones and the available commands.

## Privacy and accuracy

The temporary link is private information, as is the activity in the report.
Anyone with the URL and network access can view it until expiry. The viewer uses
HTTP: the secret path limits access but does not encrypt traffic. Use a trusted
private network or existing encrypted SSH/VPN connection. Public/all-interface
listeners are refused; do not expose the port publicly or publish a report URL.

Public source and release assets contain only generic code, examples, tests and
documentation. Account settings, credentials, notification topics, activity and
generated reports are excluded.

Version 0.2.0 introduced recording; this update preserves collected history.
Reports show fourteen local calendar dates in the server's timezone. Times are
observed presence changes, not exact Roblox login records; unavailable checks
remain unknown. Older activity cannot be reconstructed.

## Validation and remaining acceptance

Tests use real loopback HTTP connections and synthetic reports to check URL/token
isolation, headers, methods, Host validation, expiry, slow-client deadlines,
private-address validation, privilege-drop order, CLI dispatch and isolated
configuration upgrades. The full core/deployment suite also checks history,
notification deduplication, credential handling and release exclusion rules.
Server and local Python runs, optional authorization tests, and native systemd
unit verification accompany the release. No real report is included.

This remains a **preview**. Each installation must still confirm known-online API
visibility, a real online transition, phone delivery and monitoring while playing.
An offline response or push-provider acknowledgement alone cannot establish those
results. No claim of Roblox endorsement or guaranteed account/session safety,
visibility or delivery is made.
