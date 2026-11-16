Migration plan: split `users.name` into `given_name` and `family_name`
=====================================================================

Owner: Priya Raman (accounts). Reviewed by: billing, support tooling. Target window: 8 to 31 March.

## TL;DR

We store one free-text `name` per user. The tax export we owe from Q2 needs the family name
as a separate field, and email greetings currently print the full name ("Hi Maria Gonzalez,").
We add `given_name` and `family_name`, backfill them from `name`, move the code over in two
releases (the second also drops `name`). API v1 keeps returning `name` so mobile clients do not break.

## Current state

- `users` has about 62 million rows (`db/schema.sql`), PostgreSQL 14.
- `accounts-api` is the owner of the data (`src/accounts/users.py`). It runs as 8 pods
  (`deploy/accounts-api.yaml`).
- Only `accounts-api` connects to the `users` table. Everything else gets user data through
  the API or from `user.updated` events.

| Consumer | How it gets the name | Change |
|---|---|---|
| web and mobile apps | API v1 `name` field | none; v1 keeps `name` (see Compatibility) |
| billing-service | `GET /internal/users/:id` | switch to the new fields in R2 |
| email-service | `user.updated` event payload | event carries `given_name` from R1 |
| support console | API v1 | none |

## Naming rule

One rule, used by both the SQL backfill and the application code:

1. Trim leading and trailing whitespace.
2. `given_name` is everything before the first space.
3. `family_name` is everything after it, trimmed.
4. A name with no space is stored with `given_name` = the whole name and `family_name` = `''`.

We looked at splitting on the last space instead, and at an ML-based splitter. Splitting on the
first space is predictable, can be implemented identically in SQL and Python, and needs no
dependency, so we go with it. Users can correct their own names in the profile page once the
split fields are visible there (R2).

## Phases

### Phase 1: expand (migration 0044)

```sql
ALTER TABLE users
  ADD COLUMN given_name  TEXT NOT NULL DEFAULT '',
  ADD COLUMN family_name TEXT NOT NULL DEFAULT '';
```

Both defaults are constants, so on PostgreSQL 14 this is a metadata-only change
(`docs/runbooks/schema-changes.md`). The empty-string default also means every existing
`SELECT` and `INSERT` in the old code keeps working. The migration runner's 5 s `lock_timeout`
protects us from queueing behind a long query.

Exit check: columns present, old pods healthy.

### Phase 2: backfill (migration 0045)

```sql
UPDATE users
SET given_name  = split_part(btrim(name), ' ', 1),
    family_name = btrim(substr(btrim(name), length(split_part(btrim(name), ' ', 1)) + 1));
```

A single set-based statement is simpler and less error-prone than a batching loop, and it is
idempotent. On the staging copy (3.1 million rows) it takes 95 seconds; extrapolating to
production we expect about 30 minutes. We run it on Sunday 8 March at 03:00 UTC, when traffic is
about 4% of the weekday peak.

Exit check: `SELECT count(*) FROM users WHERE given_name = ''` returns 0.

### Phase 3: index (migration 0046)

The support console needs lookups by surname, so we add:

```sql
-- migrate:no-transaction
CREATE INDEX CONCURRENTLY idx_users_family_name_lower ON users (lower(family_name));
```

This is in its own migration file with the `no-transaction` header, because `CONCURRENTLY`
cannot run inside a transaction block. It runs right after the backfill, so the index is built
on populated data.

Exit check: index is valid (`indisvalid`).

### Phase 4: release R1, dual write (Tuesday 10 March)

Code changes in `src/accounts/users.py`:

- `create_user` and `update_name` call a shared `split_name()` helper and write `name`,
  `given_name` and `family_name` together.
- Reads are unchanged: everything still reads `name`.
- The `user.updated` event gains `given_name` and `family_name`.

Verification after R1 is fully rolled out: sample 1,000 random rows and check that
`given_name || ' ' || family_name` matches `name`.

### Phase 5: release R2, switch and contract (Tuesday 17 March)

R2 contains the application change and migration 0047:

```sql
ALTER TABLE users DROP COLUMN name;
```

Application changes in R2:

- All reads use `given_name` and `family_name`; nothing reads or writes `name`.
- The profile page shows two fields.
- billing-service switches to the new fields.
- The v1 API keeps a `name` field, computed as `given_name || ' ' || family_name`.

We ship the drop together with the code that stops using the column so there is no second
cleanup release to schedule. R2 goes out through the normal release pipeline.

### Phase 6: cleanup (week of 30 March)

Remove leftover references to `name` in tests and fixtures, and update the data
dictionary.

## Timeline

| Date | Step |
|---|---|
| Sun 8 Mar, 03:00 UTC | 0044, 0045, 0046 |
| Tue 10 Mar | R1 |
| Tue 17 Mar | R2 including 0047 |
| Week of 30 Mar | Cleanup |

## Compatibility

API v1 clients send and receive a single `name`. On write, v1 splits it with the naming rule.
On read, v1 returns `given_name || ' ' || family_name`. API v2 (already in development) exposes
the two fields directly and does not carry `name`.

## Risks and rollback

| Risk | Mitigation |
|---|---|
| Backfill takes longer than estimated | Sunday window leaves 3 hours; a 2x overrun still fits |
| Wrong split for some users | Users can edit their names after R2; support has a macro |
| Index build slows writes | Built `CONCURRENTLY`; it does not block writes |
| R2 regression | Roll back by redeploying the R1 build; migrations are forward-only |

## Testing

- `split_name()` has unit tests for empty input, leading and trailing spaces, and
  non-ASCII input.
- The backfill SQL and `split_name()` are compared on a 500k-row sample taken from staging;
  they must agree on every row.
- A dry run of 0044 to 0046 against a restored production snapshot, to confirm timing and the
  index.

## Communication

- Support: macro for "my name is split wrongly" ready by 6 March.
- Mobile team: informed that v1 is unchanged; v2 field names agreed.
- Data team: the data dictionary entry for `users.name` is marked deprecated at R1.

## Open questions

- When do we announce the API v1 sunset date? Needs a decision from product.
- Do we add `given_name` to the mobile push notification templates in R2 or a later release?
