# ADR-014: Append-only audit log for admin actions

Status: proposed. Deciders: platform, security. Compliance contact: records owner.

## 1. Context
Admin staff (`admin_users`, one role each: `support`, `admin` or `security_auditor`, see
`src/auth/roles.ts`) can change customer state. Today that is `suspendAccount` and
`reinstateAccount` in `src/admin/accounts.ts`; more will follow. Neither records who acted.
They emit `account.suspended` and `account.reinstated` events through the outbox. Those
events carry the account (and the reason, for suspensions) but not the actor.

Records retention policy v3 (`docs/compliance/retention-policy.md`) makes audit records a
requirement. This ADR covers privileged actions that take effect. Out of scope: denied
attempts (they change nothing, and stay in the application logs), direct database changes
made by DBAs, and cryptographic tamper-proofing (see section 10). Assumed volume: at most
300 audited actions a day, with peaks well below one per second. This is an estimate, since
the actions are not recorded today. Nothing here depends on it being exact: the sizing in
section 4 and the table growth in section 6 scale linearly, and a 100x error (30,000 a day,
12 million rows, about 12 GB) would still fit one Postgres table with its three indexes.

## 2. Requirements and how each is met

| Requirement (policy) | Mechanism | Section |
|---|---|---|
| AU-2: no action takes effect without its record | Audit row inserted in the action's own transaction | 3 |
| AU-3: who, when, what, on what, from where | Columns of `admin_audit_log` | 4 |
| AU-9: not modifiable or deletable by the actors | No UPDATE/DELETE for the service role, update-reject trigger, deletion only by a separate retention role | 4, 6 |
| AU-9: readable only by Security and Compliance | `security_auditor` role, enforced in the endpoint | 6 |
| AU-9: reads are recorded | Each search writes an `audit.search` record | 6 |
| AU-11: 400 days, deleted within 60 days of expiry | Nightly retention job | 7 |
| Copies gone within 60 days of expiry | Backups 35 days; SIEM index deleted at 400 days | 7 |

## 3. Decision: write the audit row in the action's transaction
Each admin action calls `recordAdminAction(tx, ctx, ...)` inside the same `withTransaction`
block (`src/db/tx.ts`) as the state change, after the change is known to have affected a row.
If the audit insert fails, the transaction rolls back and the admin gets an error; the
action does not happen.

This is deliberate. AU-2 says the record must be committed with the action, so a design that
writes the record afterwards, or asynchronously, has a window in which the action is in
effect without its record. Failing the action is the price of that guarantee. It adds no new
network dependency, since both writes go to the same primary database; what it adds is the
possibility of a constraint violation in the audit insert, which the tests in section 8
exercise.

Actions that match nothing are not recorded: `suspendAccount` and `reinstateAccount` return
`false` before emitting anything when their `UPDATE` changed no row, and nothing took effect.

## 4. Schema
```sql
CREATE TABLE admin_audit_log (
  id          uuid        PRIMARY KEY,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  actor_id    uuid        NOT NULL REFERENCES admin_users (id),
  action      text        NOT NULL,
  target_type text        NOT NULL,
  target_id   text        NOT NULL,
  source_ip   inet        NOT NULL,
  request_id  uuid        NOT NULL,
  details     jsonb       NOT NULL DEFAULT '{}'
);
CREATE INDEX admin_audit_log_actor_idx  ON admin_audit_log (actor_id, occurred_at DESC, id DESC);
CREATE INDEX admin_audit_log_target_idx ON admin_audit_log (target_type, target_id, occurred_at DESC, id DESC);
CREATE INDEX admin_audit_log_time_idx   ON admin_audit_log (occurred_at DESC, id DESC);

REVOKE UPDATE, DELETE, TRUNCATE ON admin_audit_log FROM app_rw;
GRANT SELECT, DELETE ON admin_audit_log TO audit_retention;
GRANT SELECT ON legal_holds TO audit_retention;
```
- `occurred_at` defaults to `now()`, which in Postgres is the transaction start time. For a
  request-scoped transaction that is within the request's duration of the commit.
- `source_ip` and `request_id` come from `AdminContext` (`src/admin/accounts.ts`).
- `actor_id` is a foreign key. An admin who has audit rows cannot be deleted; admins are
  turned off through `admin_users.disabled_at`, which the schema already provides.
- `details` holds the action's parameters, nothing else. `account.suspend` stores
  `{"reason": ...}` using the closed `SuspendReason` set; `account.reinstate` stores `{}`.
  There is no free text.
- The three indexes serve the three queries the endpoint offers (by actor, by target, by time
  range), each with keyset pagination on `(occurred_at, id)`, and the retention job's scan.
- `app_rw` receives UPDATE and DELETE on new tables through default privileges in
  `db/schema.sql`, so the `REVOKE` above is required and is part of the migration.
- A `BEFORE UPDATE` row trigger raises an exception, so that a later broad `GRANT` cannot
  silently reintroduce updates. It is a second layer; the revoked privilege is the first.
  There is no DELETE trigger because the retention job needs DELETE (section 7).

Sizing: 300 a day over 400 days is 120,000 rows, about 120 MB at an assumed 1 KB per row
including indexes (the columns themselves are a few hundred bytes, so the figure is generous).

## 5. Write path
```ts
// src/audit/record.ts (new)
export async function recordAdminAction(tx: PoolClient, ctx: AdminContext, a: AuditAction) {
  const id = randomUUID();
  const { rows } = await tx.query(
    `INSERT INTO admin_audit_log
       (id, actor_id, action, target_type, target_id, source_ip, request_id, details)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING occurred_at`,
    [id, ctx.adminId, a.action, a.targetType, a.targetId, ctx.ip, ctx.requestId,
     JSON.stringify(a.details ?? {})]);
  await emitEvent(tx, 'audit.admin_action', { id, occurred_at: rows[0].occurred_at,
    actor_id: ctx.adminId, action: a.action, target_type: a.targetType,
    target_id: a.targetId, source_ip: ctx.ip, request_id: ctx.requestId, details: a.details ?? {} });
}
```
`suspendAccount` calls it right after the `rowCount` check with action `account.suspend`,
`reinstateAccount` with `account.reinstate`. The existing `account.*` events stay as they are.
A CI check fails the build if an exported function in `src/admin/` calls `withTransaction`
without calling `recordAdminAction`. It is a text-level check and deliberately simple.

## 6. Export, access control
**Export to the SIEM.** `emitEvent` puts the audit event in the `outbox` table in the same
transaction. `relayOnce` (`src/outbox/relay.ts`) publishes rows and deletes them in one
transaction, so a crash between the publish and the commit republishes the row: delivery is
at-least-once. The SIEM consumer, `handleSiemEvent` (`src/siem/consumer.ts`), skips any
`event_id` already in `siem_export_seen`. `emitEvent` stores `event_id` in the outbox
payload, so a republished row carries the same one. We add `audit.admin_action` to
`SIEM_TOPICS`. The database stays the system of record; the SIEM copy is for search and for
an independent copy outside the database. One case remains: if `send()` succeeds and the
consumer's commit then fails, the redelivery forwards the event again. Each SIEM record
carries both `event_id` and the audit `id`, and a duplicate in the SIEM does not affect the
database, so we accept it. Audit events add about 110,000 rows a year (300 x 365) to
`siem_export_seen`; pruning can wait until that table is reviewed at its one-year mark.

**Who can write.** Rows are written by `recordAdminAction`, running as the service role
`app_rw`, which has INSERT but not UPDATE or DELETE on the table.

**Who can read.** `GET /admin/audit` calls `requireRole(ctx, 'security_auditor')`. The role
is granted to Security and Compliance staff only. `app_rw` keeps SELECT on the table because
the endpoint runs as the service role; the gate is the role check. Because each admin user
has a single role, nobody can both perform admin actions (which need `admin`) and read the
log. Before running the query the endpoint records an `audit.search` entry (target type
`audit_log`, target id `*`, the filters in `details`) in its own transaction; if that insert
fails, the search fails.

**Who can delete.** The only role granted DELETE is `audit_retention`, a login role used by
the retention job alone, with its own credential in the secrets store. No code path in
this repo changes `admin_users.role`; when one is added it must call `recordAdminAction`.

## 7. Retention
The policy sets 400 days from event time, deletion within 60 days after expiry, and a
suspension while a legal hold is active. A nightly job running as `audit_retention`:
1. Skips the run and logs it if `legal_holds` has a row with `released_at IS NULL` and
   `scope` equal to `admin_audit_log` or `all`.
2. Otherwise repeats the statement below until it deletes zero rows. The statement repeats
   the hold test, so a hold opened while the job is running stops the next batch:
```sql
DELETE FROM admin_audit_log WHERE id IN (
  SELECT id FROM admin_audit_log
   WHERE occurred_at < now() - interval '400 days'
     AND NOT EXISTS (SELECT 1 FROM legal_holds
                      WHERE released_at IS NULL AND scope IN ('admin_audit_log', 'all'))
   ORDER BY occurred_at LIMIT 5000);
```
The batch scan is served by `admin_audit_log_time_idx`, read backwards. A rows-deleted
metric and an alert after one missed night keep the real delay far inside the allowance.

Copies: a row deleted on day 401 is in backups for at most 35 more days, so it is gone about
36 days after expiry, inside the 60-day limit. The SIEM index `admin-audit` rolls over daily
and is deleted 400 days after rollover, so a record lasts at most about 401 days there; the
index setting belongs to Security and is checked in rollout step 2. Pausing the SIEM index's
deletion while a hold is open, and resuming it on release, is done by Security; this ADR
covers the database.

## 8. Tests
- After `suspendAccount`, the account is `suspended`, and one `admin_audit_log` row and one
  `audit.admin_action` outbox row exist.
- With the audit insert made to fail (an invalid `source_ip`), the account stays `active`.
- As `app_rw`, `UPDATE` and `DELETE` on `admin_audit_log` fail with permission denied. As the
  owner role, `UPDATE` hits the trigger.
- The retention job against rows backdated to 399 and 401 days deletes only the 401-day
  rows, and deletes nothing while a matching legal hold is open.
- Consumer: the same `event_id` delivered twice sends once; a throwing `send()` leaves no
  `siem_export_seen` row.

## 9. Rollout
1. A DBA creates the `audit_retention` role. Ship the migration: new table, indexes,
   trigger and grants. Nothing reads or writes the table yet.
2. Add `audit.admin_action` to `SIEM_TOPICS`. Security creates the `admin-audit` index with
   daily rollover and 400-day deletion, and confirms the setting before step 3, so that
   the first audit event already has an index to land in.
3. Deploy `recordAdminAction` in both actions plus the CI check, after the section 8 tests
   pass in staging. Because the write path fails the action, the first production deploy
   is on a weekday morning with on-call aware. Rollback is a redeploy of the previous build;
   the table and its rows stay.
4. Enable `GET /admin/audit` and grant `security_auditor` to the named staff.
5. Ship the retention job in dry-run mode (it logs the count it would delete). No row can
   reach 400 days until about 13 months after step 3, so the real deletion is switched on
   in the quarter before the first rows expire. Until then the section 8 tests are the
   evidence that it works.

There is no backfill: actions before step 3 are not in the log, and the cutover date goes in
the runbook.

## 10. Alternatives considered
- **Write audit rows from the outbox consumer.** Rejected: the outbox event commits with the
  action but the audit record would not, which does not meet AU-2.
- **Database triggers on `accounts`.** Rejected: a trigger sees the row change but not the
  actor, the reason or the intent, and every future table would need its own.
- **Hash-chaining rows.** Rejected for now: each insert would depend on the previous row's
  hash and serialise writers. The independent SIEM copy gives tamper evidence at a
  lower cost. Revisit if Security requires cryptographic proof.
- **A separate audit database or service.** Rejected: it breaks the single-transaction
  guarantee of section 3 and adds a network dependency to every action.

## 11. Open questions
- Whether `support` staff should see their own actions. AU-9 limits reads to Security and
  Compliance, so not here; Compliance can rule on it.
- Whether reading the log should need a second approver. The policy does not ask for it;
  Security may raise it separately.
