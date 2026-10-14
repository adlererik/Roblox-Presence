# Primary references consulted

Checked on 2026-10-14:

- [Roblox Creator Hub presence endpoint](https://create.roblox.com/docs/cloud/reference/domains/presence): cookie/unauthenticated legacy presence endpoint.
- [Official presence OpenAPI schema](https://presence.roblox.com/docs/json/v1): POST `/v1/presence/users`, `userIds` input, `userPresences`, `userId`, and `userPresenceType` output, enum values 0–3.
- [Official users API schema](https://users.roblox.com/docs/json/v1): public username resolution, target profile verification, and authenticated observer identity.
- [ntfy publishing](https://docs.ntfy.sh/publish/): JSON publishing, priority, topic restrictions, authentication, response messages, caching, and bearer-topic behavior.
- [ntfy Android delivery](https://docs.ntfy.sh/subscribe/phone/): notification channels, instant delivery, Google Play/FCM behavior, and foreground delivery for idle phones.
- [Pushover API](https://pushover.net/api): optional provider only; not selected for this free installation.

- [OpenRC service scripting](https://github.com/OpenRC/openrc/blob/master/service-script-guide.md) and [supervision](https://github.com/OpenRC/openrc/blob/master/supervise-daemon-guide.md): optional supervisor example.

Use the host's native service-manager tools to validate a deployment example. API visibility and device delivery require live acceptance checks for each installation; the documentation does not promise immediate or unrestricted presence access.
