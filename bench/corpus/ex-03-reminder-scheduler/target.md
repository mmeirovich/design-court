# Daily reminder emails at 9:00 local time

*Design note, growth team. Written for the 2026-11-19 review.*

## What we are building

Users who turn on "Daily reminder" in settings should get one email a day, at 9:00 in their
own timezone, listing what is due that day. About 1.4M of our 3.1M users have the setting on
(it was backfilled from the old in-app prompt), so this is a real batch workload rather than
a handful of timers.

The pieces already exist: the settings UI writes `users.reminder_enabled`, the schema has
`next_reminder_at` and `last_reminder_at` (`db/schema.sql`), the mailer is
`src/mailer.py`, and a CronJob skeleton lives in
`infra/reminders-cronjob.yaml`. What is missing is the job itself and the rules for computing
and advancing `next_reminder_at`.

## How it works

### The data

Every user has exactly one `next_reminder_at`, a `timestamptz` holding the UTC instant of
their next 9:00 local. Storing an instant, rather than "09:00" plus a zone, means the job never
does timezone maths at send time: it asks which instants have passed. It also means half-hour
and 45-minute zones (Asia/Kolkata, Asia/Kathmandu) need no special case, because there is no
bucketing by hour anywhere.

`users.timezone` is an IANA name such as `Asia/Kolkata`. We store names, not UTC offsets,
because an offset is wrong for half the year in any zone with DST. The settings page requires
a zone, so every enabled user has one.

### Scheduling a user

When a user turns reminders on, or changes their timezone, we compute the next 9:00 strictly
after now in their zone and store it as UTC:

```python
def next_nine(user, now_utc):
    tz = ZoneInfo(user.timezone)
    local = now_utc.astimezone(tz)
    candidate = datetime.combine(local.date(), time(9, 0), tzinfo=tz)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)
```

The same function does the one-off backfill for the 1.4M users who already have the setting on.
Reminders follow the profile timezone. We do not infer location from devices or IP, so a user
who travels keeps getting 9:00 home time until they change the setting.

### The tick

The CronJob runs every 5 minutes. A tick reads the users who are due and sends to each:

```python
due = db.fetch("""SELECT id, timezone FROM users
                  WHERE reminder_enabled AND next_reminder_at <= %s
                  ORDER BY next_reminder_at""", now)
with ThreadPoolExecutor(SEND_WORKERS) as pool:
    pool.map(process, due)

def process(user):
    mailer.send_template(user.id, "daily_reminder", build_context(user))
    db.execute("""UPDATE users
                  SET last_reminder_at = now(),
                      next_reminder_at = next_reminder_at + interval '24 hours'
                  WHERE id = %s""", user.id)
```

Advancing from the previous `next_reminder_at` rather than from `now()` keeps the schedule
anchored at 9:00, so send latency and tick jitter do not accumulate from day to day. Each user's
`next_reminder_at` moves forward as soon as that user has been processed, so each user is
picked up once a day. If a send fails the exception propagates before the `UPDATE`, which
leaves `next_reminder_at` where it was and the next tick retries.

Reminders more than three hours late are skipped rather than sent: `process` checks
`now - next_reminder_at` first and, if it is over three hours, only advances the schedule. A
9:00 email at 14:00 is noise.

## Sizing

Everyone's reminder is at 9:00 local, so users in the same zone become due at the same tick.
The busiest zone is America/New_York with about 150k enabled users, all due at the 14:00 UTC
tick in winter. The provider's median is about 25 ms per message (`docs/email-policy.md`), so
that tick has roughly 150,000 x 25 ms = 3,750 s of sending in it. Spread across the worker pool the
tick finishes in about 4 minutes, which fits inside the 5-minute interval with a minute to
spare. The provider limit is 500 messages per second per account, far above what this job
will push.

The due-set query returns only rows whose `next_reminder_at` has passed, so it reads about
150k rows at peak and almost none the rest of the day, however large `users` is.

## Failure handling

- **Provider outage.** Sends raise, nothing is advanced, and users are retried each tick until
  they fall outside the three-hour window, after which they skip a day.
- **Job crash mid-tick.** Users already processed have advanced `next_reminder_at`; the rest
  are picked up by the next tick.
- **Bad data.** A user whose send keeps failing is retried every 5 minutes for at most three
  hours, which is bounded and cheap.
- **Alerting.** We emit `reminders_sent`, `reminders_failed` and `tick_duration_seconds` and page
  if `tick_duration_seconds` exceeds 240 for two ticks in a row.

## Who gets an email

Anyone with `reminder_enabled = true` and a due `next_reminder_at`. The toggle is the
user's explicit request for the email, so reminders are sent to everyone who has it on.
Content is plain: a list of the user's items due that day and a link to the app.

## Rollout

1. Backfill `next_reminder_at` for enabled users with the `next_nine` function, in batches of
   10,000 ids to keep transactions short.
2. Ship the job behind `daily_reminders` for users where `id % 50 = 0` (about 2%) for one week.
   Watch send failures, unsubscribe rate and `tick_duration_seconds`.
3. Raise to 25%, then 100%, two days apart.
4. Turn off the old in-app prompt once 100% has run for a week.

## Alternatives we rejected

- **One CronJob per timezone.** There are about 400 zones in use, and DST moves each zone's
  UTC offset twice a year, so every one of those schedules would need to be edited twice a year.
- **Per-user delayed messages on the queue.** Elegant, but a timezone or setting change means
  finding and cancelling a pending message, and the queue gives no way to look one up by user.
- **Bucket users by UTC offset and run hourly.** Wrong for half-hour zones and for the weeks when
  the US and Europe are on different DST schedules.

## Not in scope

Digest content personalisation, per-user send times, SMS or push reminders, and any quiet-hours
feature. All of these can reuse `next_reminder_at` as the single scheduling field.

## Open questions

- Should the email include a one-click "snooze for a week"? It would be a new endpoint that
  sets `next_reminder_at`. Growth wants to see the unsubscribe rate first.
- Do we want a Grafana panel of sends per zone, or is the aggregate enough for launch?
