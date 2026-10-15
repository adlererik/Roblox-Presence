# Roblox Presence Monitor 0.3.0 — a bookmarked private dashboard

Generate and view fourteen-day activity graphs from a phone or desktop browser.
After one administrator setup, open your private bookmark and tap **Generate new
graph**. There is no terminal to keep open and no everyday sudo requirement.

- **A stable secret URL:** the latest saved graph remains until replaced. New
  graphs use the same URL. The key and saved graph survive monitor restarts and
  upgrades; the server's address/port must remain available.
- **Phone generation:** a progress indicator and automatic refresh show the new
  snapshot. A normal form is also available without JavaScript. One job at a time
  and a ten-second request floor limit repeated generation.
- **Regular-user commands:** `robox graph`, `robox dashboard`, `robox status` and
  `robox --help` use the selected operator's private client settings. They need
  no root config, database access or Roblox cookie. `graph --file-only` and
  `--output` download a fresh self-contained HTML copy.
- **Readable recorded times:** select a day to see online/offline observations
  with full dates, hours, minutes, seconds, timezone and UTC offset. Offline rows
  show the first offline check and its later confirmation. All clocks follow the
  server timezone, including daylight saving, on phone and desktop alike.
- **Isolated setup:** the existing unprivileged monitor gains a restricted
  dashboard thread. Setup creates only its private key, operator client and own
  systemd drop-in, with one specific high TCP port/address family allowed. Only
  this monitor is restarted. Existing websites, proxies, firewall/router settings,
  other service units and global sudo rules are unchanged.

Follow the [beginner guide](GETTING_STARTED.md) for a new installation,
the [guarded upgrade guide](ACTIVITY.md#updating-an-existing-systemd-installation)
for an existing systemd server, or the [dashboard guide](DASHBOARD.md) for everyday
phone use, setup details and other supervisors.

## Privacy and accuracy

The URL is a persistent bearer secret granting viewing and generation. Anyone
with it and network access can use it until the administrator replaces the key.
HTTP does not encrypt traffic. Use a trusted private network or existing encrypted
VPN/SSH connection; never forward the port publicly or publish the link.

The restricted API has no credential, file-browser, arbitrary query or account
management route. Generation requires a same-origin form and separate CSRF nonce.
Requests have deadlines and no access logs. Responses prohibit caching, referrers
and framing. Downloaded HTML contains no key or active control form. The service
retains its resource restrictions; dashboard opt-in raises only its memory cap to
256 MiB for large reports, with a separate lower-priority graph process limited to 128 MiB of address space, eight CPU seconds (ten-second hard limit) and sixty elapsed seconds.

Times are precise **observations**, not an exact Roblox login/logout audit. Checks
normally run every fifteen seconds; API and network delays add uncertainty.
Unknown intervals remain unknown. History collected since 0.2.0 is preserved;
earlier activity cannot be reconstructed. Public assets include only generic code,
tests, examples and documentation, with no operator data or generated reports.

## Validation and remaining acceptance

Tests cover real HTTP generation/CSRF/headers/paths, browser form charset handling,
saved graphs and stable links across restarts, failed/throttled generation, exact
observed online/offline timestamps, non-root CLI/file privacy, configuration and
unit isolation, occupied-port refusal, and monitoring after dashboard startup
failure. Existing history, credential, notification/retry and packaging checks
remain part of the suite. Browser checks use synthetic data and exercise the
generation button, phone layout and date-filter/reset behavior. The packaged
Python suite is exercised locally and on Debian; native unit verification and
the separate optional authorization tests are included.

This remains a **preview**. Each installation must verify known-online Roblox
visibility, a real online transition, phone receipt and monitoring while playing.
An offline reply or provider acknowledgement alone cannot establish those results.
The OpenRC example is syntax checked, not live validated. No Roblox endorsement,
guaranteed delivery or guaranteed account/session safety is claimed.
