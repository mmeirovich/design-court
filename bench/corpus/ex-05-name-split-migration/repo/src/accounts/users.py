"""User persistence for accounts-api."""
from db import pool


def get_user(user_id: int) -> dict | None:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id, email, name, locale FROM users WHERE id = %s", (user_id,)
        ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "email": row[1], "name": row[2], "locale": row[3]}


def create_user(user_id: int, email: str, name: str, locale: str = "en") -> None:
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO users (id, email, name, locale) VALUES (%s, %s, %s, %s)",
            (user_id, email, name, locale),
        )


def update_name(user_id: int, name: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            "UPDATE users SET name = %s, updated_at = now() WHERE id = %s",
            (name, user_id),
        )


def touch_last_seen(user_id: int) -> None:
    """Called on every successful login and token refresh."""
    with pool.connection() as conn:
        conn.execute("UPDATE users SET last_seen_at = now() WHERE id = %s", (user_id,))
