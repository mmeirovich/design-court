# Schema changes on the primary database

Applies to PostgreSQL 14 and the migration runner in `db/migrate.py`.

## Adding columns
- `ADD COLUMN` with no default, or with a constant default, is a metadata-only change and
  does not rewrite the table (PostgreSQL 11 and later). A volatile default
  (`now()`, `random()`, a function call) rewrites the whole table and takes an
  `ACCESS EXCLUSIVE` lock for the duration.
- `ALTER TABLE` statements need a brief `ACCESS EXCLUSIVE` lock. The runner sets
  `lock_timeout` to 5 s so a blocked migration fails rather than queueing behind a
  long query and stalling every other session on the table.

## Indexes
- Build indexes on populated tables with `CREATE INDEX CONCURRENTLY`. It cannot run inside
  a transaction block, so put it in its own migration file starting with
  `-- migrate:no-transaction`.

## Long transactions
- `users` and `orders` take writes on every request path (`users.last_seen_at` is updated on
  each login). Keep transactions that write to them under 30 seconds. An open transaction
  that has updated a row holds that row's lock until it commits; other sessions that update
  the same row wait.
- Large updates also generate WAL that streams to the replicas; a single multi-million-row
  statement can put the replicas minutes behind.

## Deploys
- Migrations are applied by the release's migration job before the application rollout
  begins. See `deploy/` for each service's rollout strategy.
