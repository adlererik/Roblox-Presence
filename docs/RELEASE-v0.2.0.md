# Roblox Presence Monitor 0.2.0 — activity graph preview

A consenting Roblox connection coming online can trigger a phone notification,
so you can open Roblox and play together. This release adds a private fourteen-day
activity overview, readable server-local clock times, and easier commands.

- **Activity graph:** `sudo robox graph` saves a self-contained HTML report. One
  row per day, online-time totals, gaps for unavailable checks, and date filtering
  make activity easy to scan. A detailed list shows detected login/logout times
  with seconds, timezone and UTC offset. Phone and desktop layouts are supported.
- **Easy help:** `robox --help` explains every command. `roblox` is an equivalent
  spelling. Help works without configuration or administrator permissions.
- **Richer notifications:** player display name, username, visible game name and
  server-local observation time. One first-game follow-up is possible if the
  initial online alert had no game; later game switches stay silent. Hidden game
  data is never looked up or guessed.
- **Guarded upgrade:** backs up the SQLite database, preserves credentials and
  durable alert/retry state, switches only this application's release, restarts
  only this service, and checks fresh health and other running services.

For a new server, follow the [beginner installation guide](GETTING_STARTED.md).
Existing installations should use the [upgrade guide](ACTIVITY.md#updating-an-existing-systemd-installation).
The [activity and command guide](ACTIVITY.md) explains how to generate, download
and open the report without exposing a new web service.

## Accuracy and privacy

History starts when this version runs. Earlier activity cannot be recovered.
These are observation times, not exact Roblox account login/logout records.
Checks normally run every fifteen seconds and can be delayed or interrupted.
Unknown intervals remain visibly unknown. Reports cover fourteen local calendar
dates including today; local checks are retained for fifteen elapsed days to
cover timezone/clock-change boundaries. Downloaded files and private upgrade
backups remain until the operator removes them.

The push provider now receives player/game names and observed times. Keep the
notification topic and report files private. HTML exports are mode 0600 and omit
credentials, topics, numeric account IDs, and place/server IDs. Public source and
release assets include only generic code, examples, tests and documentation.

## Validation and remaining acceptance

The Python suite covers migration, history/gap accuracy, retention, DST changes,
private report exports, notification deduplication/follow-ups, retry floors,
credential security, source packaging and isolated upgrades. Browser previews use
synthetic data and cover phone/desktop layouts and date filtering/reset. The
optional authorization helper has separate Node tests. The systemd unit has
native verification; the OpenRC example has syntax checks only.

This remains a **preview**. A real known-online API comparison, actual online
transition alert, playing while monitoring and each installation's phone delivery
must still be checked. Existing live offline and locked-phone test results do not
prove a new real online transition. No claim of Roblox endorsement, guaranteed
session lifetime or guaranteed notification delivery is made.
