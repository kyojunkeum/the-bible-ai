import base64
import hashlib
import os

from psycopg2.extras import RealDictCursor

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover - optional dependency
    Fernet = None
    InvalidToken = Exception


_FERNET = None
_FERNET_READY = False


def _get_fernet():
    global _FERNET, _FERNET_READY
    if _FERNET_READY:
        return _FERNET
    secret = os.getenv("OPENAI_KEY_ENCRYPTION_SECRET", "")
    if not secret or Fernet is None:
        _FERNET_READY = True
        _FERNET = None
        return None
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    _FERNET = Fernet(key)
    _FERNET_READY = True
    return _FERNET


def _encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    fernet = _get_fernet()
    if not fernet:
        return value
    return fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def _decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    fernet = _get_fernet()
    if not fernet:
        return value
    try:
        return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def ensure_user_settings(conn, user_id: str) -> dict:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO user_settings (user_id, store_messages, openai_citation_enabled, openai_api_key)
            VALUES (%s, FALSE, FALSE, NULL)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id,),
        )
        cur.execute(
            """
            SELECT user_id, store_messages, openai_citation_enabled, openai_api_key, updated_at
            FROM user_settings
            WHERE user_id = %s
            """,
            (user_id,),
        )
        return cur.fetchone()


def get_user_settings(conn, user_id: str, include_secrets: bool = False) -> dict:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT user_id, store_messages, openai_citation_enabled, openai_api_key, updated_at
            FROM user_settings
            WHERE user_id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if row:
            if include_secrets:
                row["openai_api_key"] = _decrypt_secret(row.get("openai_api_key"))
            return row
    row = ensure_user_settings(conn, user_id)
    if include_secrets and row:
        row["openai_api_key"] = _decrypt_secret(row.get("openai_api_key"))
    return row


def update_user_settings(
    conn,
    user_id: str,
    store_messages: bool | None = None,
    openai_citation_enabled: bool | None = None,
    openai_api_key: str | None = None,
) -> dict:
    current = get_user_settings(conn, user_id)
    next_store = current.get("store_messages", False) if store_messages is None else store_messages
    next_openai_enabled = (
        current.get("openai_citation_enabled", False)
        if openai_citation_enabled is None
        else openai_citation_enabled
    )
    next_key = current.get("openai_api_key")
    if openai_api_key is not None:
        cleaned = openai_api_key.strip()
        next_key = _encrypt_secret(cleaned) if cleaned else None
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO user_settings (user_id, store_messages, openai_citation_enabled, openai_api_key)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET
              store_messages = EXCLUDED.store_messages,
              openai_citation_enabled = EXCLUDED.openai_citation_enabled,
              openai_api_key = EXCLUDED.openai_api_key,
              updated_at = now()
            RETURNING user_id, store_messages, openai_citation_enabled, openai_api_key, updated_at
            """,
            (user_id, next_store, next_openai_enabled, next_key),
        )
        return cur.fetchone()
