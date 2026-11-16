"""Incrementally index users into the search cluster.

Runs every 5 minutes from cron. Reads from the read replica with the
`search_ro` role.
"""
import os

import psycopg

from search_client import bulk_upsert

CURSOR_FILE = "/var/lib/search-indexer/users.cursor"
BATCH = 5000


def load_cursor() -> str:
    try:
        return open(CURSOR_FILE).read().strip()
    except FileNotFoundError:
        return "1970-01-01T00:00:00+00"


def main() -> None:
    cursor = load_cursor()
    with psycopg.connect(os.environ["REPLICA_DSN"]) as conn:
        while True:
            rows = conn.execute(
                "SELECT id, email, name, locale, updated_at FROM users "
                "WHERE updated_at > %s ORDER BY updated_at LIMIT %s",
                (cursor, BATCH),
            ).fetchall()
            if not rows:
                break
            bulk_upsert(
                "users",
                [{"id": r[0], "email": r[1], "name": r[2], "locale": r[3]} for r in rows],
            )
            cursor = rows[-1][4].isoformat()
            open(CURSOR_FILE, "w").write(cursor)


if __name__ == "__main__":
    main()
