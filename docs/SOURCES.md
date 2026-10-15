# Primary references consulted

API/deployment references checked on 2026-10-14; account-policy, browser, and
beginner setup references checked on 2026-10-15:

- [Roblox Creator Hub presence endpoint](https://create.roblox.com/docs/cloud/reference/domains/presence): cookie/unauthenticated legacy presence endpoint.
- [Official presence OpenAPI schema](https://presence.roblox.com/docs/json/v1): POST `/v1/presence/users`, `userIds` input, `userPresences`, `userId`, and `userPresenceType` output, enum values 0–3.
- [Official users API schema](https://users.roblox.com/docs/json/v1): public username resolution, target profile verification, and authenticated observer identity.
- [ntfy publishing](https://docs.ntfy.sh/publish/): JSON publishing, priority, topic restrictions, authentication, response messages, caching, and bearer-topic behavior.
- [ntfy Android delivery](https://docs.ntfy.sh/subscribe/phone/): notification channels, instant delivery, Google Play/FCM behavior, and foreground delivery for idle phones.
- [Pushover API](https://pushover.net/api): optional provider only; not selected for this free installation.

- [OpenRC service scripting](https://github.com/OpenRC/openrc/blob/master/service-script-guide.md) and [supervision](https://github.com/OpenRC/openrc/blob/master/supervise-daemon-guide.md): optional supervisor example.
- [Systemd credential ACL behavior](https://github.com/systemd/systemd/issues/29435): dynamic-user snapshots may report mode `0440` because the group mode field represents the ACL mask. Access remains limited to root and the service's individual UID; a mode-only rejection is incompatible with this mechanism.

- [Roblox terms effective 19 May 2026](https://en.help.roblox.com/hc/en-us/article_attachments/54069120817172): current at the October check date, including documented API access and enforcement. The announced 1 November 2026 terms update is future-dated, not the current policy at this check.
- [Creator Third Party App Policy](https://en.help.roblox.com/hc/en-us/articles/37924211313044-Creator-Third-Party-App-Policy): restrictions on tracking and identifying-information disclosure, and exceptions described for official consent settings. An exception is not evidence that this project is approved.
- [Roblox error 264](https://en.help.roblox.com/hc/en-us/articles/36665660855700-Error-Code-264-Same-account-launched-experience-from-different-devices): simultaneous game access. The conclusion that a read-only API monitor is not a second gameplay session is an inference from this explanation and the code.
- [Keep Your Account Safe](https://en.help.roblox.com/hc/en-us/articles/203313380-Keep-Your-Account-Safe): Roblox warns against sharing cookies. Self-hosting this monitor still requires protecting a full account session; it does not provide a limited-scope authorization.
- [Roblox's cookie-format and rotation announcement](https://devforum.roblox.com/t/upcoming-roblosecurity-cookie-format-changes/4328913): Roblox staff instruct custom clients to preserve `Set-Cookie` updates; changes began on or after May 2026. Rotation support does not prevent Roblox from invalidating a session for other reasons.
- [Official Quick Login instructions](https://en.help.roblox.com/hc/en-us/articles/360056582012-Quick-Login): phone approval of a new device grants full account access, uses short-lived codes, requires nearby devices, and is not available to every account. The linked code-entry page can fail; do not assume a phone/app route works until it has been checked.
- [Firefox Storage Inspector](https://firefox-source-docs.mozilla.org/devtools-user/storage_inspector/index.html) and [Chrome cookie inspection](https://developer.chrome.com/docs/devtools/application/cookies): built-in browser controls used in the secure local setup walkthrough.
- [ntfy terms](https://docs.ntfy.sh/terms/): free use is subject to limits; Android receipt must still be tested on the intended device.

Use the host's native service-manager tools to validate a deployment example. API visibility and device delivery require live acceptance checks for each installation; the documentation does not promise immediate or unrestricted presence access.
