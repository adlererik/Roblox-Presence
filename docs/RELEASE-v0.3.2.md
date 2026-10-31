# Roblox Presence Monitor 0.3.2 — thirty-day activity chart

The activity chart now covers the last **30 local calendar dates, including today**.
Each date has a timeline; selecting it shows the recorded online/offline times
with hours, minutes, seconds and the server timezone. The chart heading, browser
title, date-filter reset and command help all describe the same thirty-day window.

Presence checks are retained for **31 elapsed days**, allowing for local midnight
and daylight-saving changes. Upgrades preserve existing records, notification
state, credentials and the persistent private dashboard URL. Checks already
removed by the previous fifteen-day retention policy cannot be recovered; those
dates stay unknown while the longer window fills. A saved graph remains unchanged
until a new graph is generated.

## Updating an existing installation

Follow the [upgrade guide](ACTIVITY.md#updating-an-existing-systemd-installation)
using this release in a new source directory. Administrator access is needed only
for the upgrade; everyday graph commands continue to run without sudo after the
[dashboard setup](DASHBOARD.md).

After updating, open your bookmarked dashboard and tap **Generate new graph**, or
run `robox graph` in your server terminal. Your browser link stays the same.
New installations use the [plain-language installation guide](GETTING_STARTED.md).
The upgrade backs up state and restarts only this monitor.

## Verification

The full 138-test Python suite covers calendar boundaries across spring/autumn
clock changes, precise observed event times, inclusion of checks older than
fourteen days, the thirty-one-day pruning boundary, private dashboard generation,
and existing notification and credential behavior. The package is tested locally
and on Debian. A synthetic full month of checks, including the autumn clock
change, renders in the existing isolated worker without increasing its memory,
CPU or output limits. Public source and release assets contain generic examples
only, with no operator configuration or credentials.

This remains a preview. Times are recorded observations, not Roblox login/logout
audit records. Complete real known-online visibility and phone-delivery checks
before relying on an installation.
