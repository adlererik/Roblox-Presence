# Roblox Presence Monitor 0.3.1 — dashboard setup repair

The 0.3.0 installer could stop before activation when an operator's existing
`.config` directory allowed group writing. This patch accepts that user-owned
shared parent without changing its permissions. The monitor's own subfolder
remains private (0700), with a private client file (0600).

- Complete the operator-owned step before writing the dashboard key/drop-in.
- Return safe, useful setup errors from the privilege-dropping child.
- Recover a stopped preparation only when its drop-in exactly matches the
  generated configured or requested port/address family. Custom files are refused.
- Preserve the existing protected key, credentials, state and earlier prepared
  files. Upgrade from running 0.2.x or 0.3.0 using the new release's source;
  do not rerun first installation or remove state as a repair.

The [upgrade guide](ACTIVITY.md#updating-an-existing-systemd-installation) prepares
only this monitor. The [dashboard guide](DASHBOARD.md) explains recovery and phone
use. New installations follow the [beginner guide](GETTING_STARTED.md).

Regression tests cover the shared-parent permissions, neighboring app settings,
private client permissions, refused setup without privileged dashboard writes,
and a complete upgrade from a matching partial preparation while preserving its
key and files. The full suite is exercised locally and on Debian, with native
systemd verification. Public source/assets contain only generic code, tests,
examples and documentation.

This remains a preview. Graph times are recorded observations, usually checked
every fifteen seconds, rather than exact Roblox login/logout records. Existing
known-online visibility and real notification acceptance checks remain necessary.
The private dashboard URL is a persistent secret for trusted private-network or
existing encrypted VPN/SSH access; HTTP does not encrypt traffic.
