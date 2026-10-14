# Project instructions

This is a general-purpose Roblox presence monitor for Linux. Public source and
examples must remain independent of any operator's relationships, account names,
hostnames, devices, addresses, or personal paths. Operator-specific setup belongs
in ignored local files; do not copy those files or credentials into releases.

- Preserve all existing production applications. Do not restart, reconfigure, or
  deploy unrelated services, change firewall/proxy settings, or reboot the server.
- Keep this monitor under its dedicated `/opt/roblox-presence`,
  `/etc/roblox-presence`, `/var/lib/roblox-presence`, and service-unit paths.
- Deployment preparation does not mean activating the service. Complete the real
  account visibility and Android receipt checks before treating it as operational.
- Never print or commit Roblox cookies, ntfy topics/tokens, or private setup files.
  Prompt for the observer's own credential in a terminal or use protected files.
- Preserve the rule that failures are unknown, never offline; preserve durable
  notification deduplication and provider backoff across restarts.
- Run `python3 -m unittest discover -v` for substantive code changes. The application
  uses the standard library; do not add runtime dependencies without a concrete need.
