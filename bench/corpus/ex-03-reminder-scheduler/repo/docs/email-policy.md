# Email policy

## Categories

**Transactional**: receipts, password resets, security alerts, account-closure notices.
These are sent regardless of opt-out.

**Everything else** (digests, product news, nudges, any new notification type) is treated as
promotional until Legal has classified it in writing. Promotional email must not be sent to
a user with `users.email_opt_out_at` set. Every promotional email carries the one-click
unsubscribe link, which sets `email_opt_out_at`.

## Sending

- Use `mailer.send_template`; do not call the provider directly.
- Provider limits: 500 messages per second per account, 2 s request timeout. Median
  latency per message is about 25 ms from our region.
- Per-template opt-in toggles (such as `reminder_enabled`) are in addition to the rules
  above, not a replacement for them.
