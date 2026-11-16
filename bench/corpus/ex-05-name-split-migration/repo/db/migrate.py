"""Apply db/migrations/*.sql in filename order.

Each file runs in its own transaction. A file whose first line is
`-- migrate:no-transaction` runs in autocommit mode instead (needed for
statements such as CREATE INDEX CONCURRENTLY). Applied versions are recorded
in schema_migrations.
"""
import pathlib
import sys

import psycopg

MIGRATIONS = pathlib.Path(__file__).parent / "migrations"


def applied(conn) -> set[str]:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY)")
    return {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}


def run_file(dsn: str, path: pathlib.Path) -> None:
    sql = path.read_text()
    no_tx = sql.splitlines()[0].strip() == "-- migrate:no-transaction"
    with psycopg.connect(dsn, autocommit=no_tx) as conn:
        if not no_tx:
            conn.execute("SET LOCAL lock_timeout = '5s'")
        conn.execute(sql)
        conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,))


def main(dsn: str) -> None:
    with psycopg.connect(dsn) as conn:
        done = applied(conn)
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.stem in done:
            continue
        print(f"applying {path.name}")
        run_file(dsn, path)


if __name__ == "__main__":
    main(sys.argv[1])
