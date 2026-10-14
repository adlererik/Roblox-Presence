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

- [Roblox terms effective 19 May 2026](https://en.help.roblox.com/hc/en-us/article_attachments/54069120817172): current at the October check date, including documented API access and enforcement. The announced 1 November 2026 terms update is future-dated, not the current policy at this check.
- [Creator Third Party App Policy](https://en.help.roblox.com/hc/en-us/articles/37924211313044-Creator-Third-Party-App-Policy): restrictions on tracking and identifying-information disclosure, and exceptions described for official consent settings. An exception is not evidence that this project is approved.
- [Roblox error 264](https://en.help.roblox.com/hc/en-us/articles/36665660855700-Error-Code-264-Same-account-launched-experience-from-different-devices): simultaneous game access. The conclusion that a read-only API monitor is not a second gameplay session is an inference from this explanation and the code.
- [Keep Your Account Safe](https://en.help.roblox.com/hc/en-us/articles/203313380-Keep-Your-Account-Safe): Roblox warns against sharing cookies. Self-hosting this monitor still requires protecting a full account session; it does not provide a limited-scope authorization.
- [Firefox Storage Inspector](https://firefox-source-docs.mozilla.org/devtools-user/storage_inspector/index.html) and [Chrome cookie inspection](https://developer.chrome.com/docs/devtools/application/cookies): built-in browser controls used in the secure local setup walkthrough.
- [ntfy terms](https://docs.ntfy.sh/terms/): free use is subject to limits; Android receipt must still be tested on the intended device.

Use the host's native service-manager tools to validate a deployment example. API visibility and device delivery require live acceptance checks for each installation; the documentation does not promise immediate or unrestricted presence access.
