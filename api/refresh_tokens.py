from datetime import datetime, timezone
from psycopg2.extras import RealDictCursor

from api.jwt_utils import exp_to_datetime, hash_refresh_id


def store_refresh_token(conn, user_id: str, refresh_id: str, exp_ts: int, device_id: str | None) -> None:
    token_hash = hash_refresh_id(refresh_id)
    expires_at = exp_to_datetime(exp_ts)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO auth_refresh_token (refresh_id, user_id, token_hash, device_id, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (refresh_id, user_id, token_hash, device_id, expires_at),
        )


def get_refresh_token(conn, refresh_id: str) -> dict | None:
    token_hash = hash_refresh_id(refresh_id)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT refresh_id, user_id, token_hash, device_id, created_at, expires_at, revoked_at
            FROM auth_refresh_token
            WHERE refresh_id = %s AND token_hash = %s
            """,
            (refresh_id, token_hash),
        )
        return cur.fetchone()


def revoke_refresh_token(conn, refresh_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE auth_refresh_token
            SET revoked_at = now()
            WHERE refresh_id = %s AND revoked_at IS NULL
            """,
            (refresh_id,),
        )


def is_refresh_token_active(row: dict) -> bool:
    if not row:
        return False
    if row.get("revoked_at"):
        return False
    expires_at = row.get("expires_at")
    if not expires_at:
        return False
    if isinstance(expires_at, datetime):
        now = datetime.now(timezone.utc)
        return expires_at > now
    return False
