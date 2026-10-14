# Verification

## Automated coverage

Run the suite with `python3 -m unittest discover -v`. Tests use synthetic account IDs, fixture credentials, temporary state directories, and mocked API responses; they do not require a real session or publish notifications.

Coverage includes:

- Observer identity validation, presence types, missing/unknown responses, authentication failure, CSRF handling, and rate limiting.
- New-session detection, offline confirmation, unknown observations, restart deduplication, scoped state, and process locking.
- Persistent delivery retries, server retry floors, stale/expired alerts, cancellation, acknowledgement validation, and outage/recovery events.
- Credential permissions, symlink/FIFO rejection, bounded network responses, safe logs, and graceful worker shutdown.
- Isolated systemd installer behavior, dry-run/collision protection, direct file-based configuration, supervisor-independent preflight, and release exclusion/reproducibility checks.

The core suite has been exercised on Linux with Python 3.13 and 3.14. The systemd unit has passed native unit verification with systemd 257. The OpenRC example is syntax checked; real OpenRC activation is not included in those results. These checks do not certify every distribution, service-manager version, or device.

## Live acceptance checks for each installation

1. Confirm the authenticated observer ID and intended connection ID.
2. Compare the API with manual Roblox visibility during a known online session.
3. Observe a real offline to online transition and confirm one notification.
4. Verify device receipt while locked/idle and on the relevant networks.
5. Restart only this monitor and check that the same observed session is not announced again.
6. Test source/push failure and recovery without exposing credentials or disrupting other applications.
7. Validate startup, shutdown, credential permissions, state persistence, supervision, and resource use on the intended host.

Mock tests cannot prove API visibility or device delivery. A push-provider acknowledgement proves acceptance only. Store account-specific results, addresses, inventory, and logs outside Git in private operational files.
