# Verification

## Automated coverage

Run the suite with `python3 -m unittest discover -v`. Tests use synthetic account IDs, fixture credentials, temporary state directories, and mocked API responses; they do not require a real session or publish notifications.

Coverage includes:

- Observer identity validation, presence types, missing/unknown responses, authentication failure, CSRF handling, and rate limiting.
- Preservation of multiple `Set-Cookie` headers, protected session rotation across restarts, source refresh precedence, current-credential export, and invalid/mismatched rotation rejection.
- New-session detection, offline confirmation, unknown observations, restart deduplication, scoped state, and process locking.
- Persistent delivery retries, server retry floors, stale/expired alerts, cancellation, acknowledgement validation, and outage/recovery events.
- Credential permissions, symlink/FIFO rejection, bounded network responses, safe logs, push payloads without identifying profile links, and graceful worker shutdown.
- Native POSIX credential ACLs for dynamic service identities, including rejection of other users, group/world grants, malformed ACLs, and ordinary group-readable files.
- Isolated systemd installer behavior, service configuration through protected credentials, dry-run/collision protection, direct file-based configuration, supervisor-independent preflight, and release exclusion/reproducibility checks.
- Additive schema migration, bounded history retention, confirmed logout timestamps, no invented logout during failures, read-only scoped reporting, DST transitions, HTML escaping/CSP, private atomic report exports, and both CLI spellings.
- One first-game follow-up per session, pending-alert enrichment, silent startup, cancellation and durable game notification metadata, with optional profile retry floors.
- Monitor-only upgrade selection, a real SQLite backup and release switch in an isolated filesystem, unchanged credentials/units, and command collision protection.
- Release Git exclusion rules, refusal of source symlinks, and an untracked private canary that must never enter the archive.

The core suite has been exercised on Linux with Python 3.13 and 3.14. The systemd unit has passed native unit verification with systemd 257. The OpenRC example is syntax checked; real OpenRC activation is not included in those results. These checks do not certify every distribution, service-manager version, or device.

The optional browser authorization helper has separate Node.js checks:
`node --test tests/test_quick_login.cjs`. They cover displayed-code parsing,
observer mismatch rejection, credential validation, and atomic private saving.
The official login page and Quick Sign-in code popup have been exercised in a
sandboxed headless browser; that does not prove phone approval for every account.

The 0.2.0 report was also checked in a browser at desktop and phone widths, including date filtering/reset and a full-day timeline that fits the phone. These previews use synthetic activity, never a real account history.

## Live acceptance checks for each installation

1. Confirm the authenticated observer ID and intended connection ID.
2. Compare the API with manual Roblox visibility during a known online session.
3. Observe a real offline to online transition and confirm one notification.
4. Verify device receipt while locked/idle and on the relevant networks.
   While the monitor runs, join a game normally with the observer account and
   confirm presence checks remain healthy on the intended host.
5. Restart only this monitor and check that the same observed session is not announced again.
6. Test source/push failure and recovery without exposing credentials or disrupting other applications.
7. Validate startup, shutdown, credential permissions, state persistence, supervision, and resource use on the intended host.

Mock tests cannot prove API visibility or device delivery. A push-provider acknowledgement proves acceptance only. Store account-specific results, addresses, inventory, and logs outside Git in private operational files.
