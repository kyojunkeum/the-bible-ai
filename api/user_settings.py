from psycopg2.extras import RealDictCursor


def ensure_user_settings(conn, user_id: str) -> dict:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO user_settings (user_id, store_messages)
            VALUES (%s, FALSE)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id,),
        )
        cur.execute(
            """
            SELECT user_id, store_messages, updated_at
            FROM user_settings
            WHERE user_id = %s
            """,
            (user_id,),
        )
        return cur.fetchone()


def get_user_settings(conn, user_id: str) -> dict:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT user_id, store_messages, updated_at
            FROM user_settings
            WHERE user_id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if row:
            return row
    return ensure_user_settings(conn, user_id)


def update_user_settings(conn, user_id: str, store_messages: bool) -> dict:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO user_settings (user_id, store_messages)
            VALUES (%s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET store_messages = EXCLUDED.store_messages, updated_at = now()
            RETURNING user_id, store_messages, updated_at
            """,
            (user_id, store_messages),
        )
        return cur.fetchone()
