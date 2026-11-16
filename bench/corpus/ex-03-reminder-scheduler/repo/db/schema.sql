-- ~3.1M rows
CREATE TABLE users (
    id                BIGSERIAL PRIMARY KEY,
    email             TEXT NOT NULL,
    display_name      TEXT,
    -- IANA zone name chosen on the settings page, e.g. 'Europe/Berlin'.
    -- NULL for accounts created before the picker shipped (April 2023), which is
    -- about 11% of rows, and for some mobile-web signups.
    timezone          TEXT,
    email_opt_out_at  TIMESTAMPTZ,
    -- Set from the settings page. Also backfilled to TRUE for users who had accepted the
    -- old in-app daily-reminder prompt, which did not ask for a timezone.
    reminder_enabled  BOOLEAN NOT NULL DEFAULT FALSE,
    next_reminder_at  TIMESTAMPTZ,
    last_reminder_at  TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX users_email_key ON users (lower(email));

-- Added with the reminder settings UI.
CREATE INDEX users_reminder_due_idx
    ON users (next_reminder_at)
    WHERE reminder_enabled AND next_reminder_at IS NOT NULL;
