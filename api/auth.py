import base64
import hashlib
import hmac
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from psycopg2.extras import RealDictCursor


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PBKDF2_ITERATIONS = 120_000
SESSION_DAYS = 30
AUTH_PEPPER = os.getenv("AUTH_PEPPER", "")
AUTH_CAPTCHA_BYPASS = os.getenv("AUTH_CAPTCHA_BYPASS", "")
ARGON2_TIME_COST = int(os.getenv("ARGON2_TIME_COST", "2"))
ARGON2_MEMORY_COST = int(os.getenv("ARGON2_MEMORY_COST", "102400"))
ARGON2_PARALLELISM = int(os.getenv("ARGON2_PARALLELISM", "8"))
ARGON2_HASH_LEN = int(os.getenv("ARGON2_HASH_LEN", "32"))
ARGON2_SALT_LEN = int(os.getenv("ARGON2_SALT_LEN", "16"))

LOGIN_FAIL_DELAY_THRESHOLD = int(os.getenv("AUTH_FAIL_DELAY_THRESHOLD", "5"))
LOGIN_FAIL_DELAY_SECONDS = int(os.getenv("AUTH_FAIL_DELAY_SECONDS", "30"))
LOGIN_CAPTCHA_THRESHOLD = int(os.getenv("AUTH_CAPTCHA_THRESHOLD", "10"))

PASSWORD_HASHER = PasswordHasher(
    time_cost=ARGON2_TIME_COST,
    memory_cost=ARGON2_MEMORY_COST,
    parallelism=ARGON2_PARALLELISM,
    hash_len=ARGON2_HASH_LEN,
    salt_len=ARGON2_SALT_LEN,
)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str) -> bool:
    if not email:
        return False
    return bool(EMAIL_PATTERN.match(email))


def _pepper_password(password: str) -> str:
    if not AUTH_PEPPER:
        return password
    return f"{password}{AUTH_PEPPER}"


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(_pepper_password(password))


def _verify_pbkdf2(password: str, stored: str) -> bool:
    try:
        algo, iter_text, salt_b64, digest_b64 = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iter_text)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("pbkdf2_sha256$"):
        return _verify_pbkdf2(password, stored)
    try:
        return PASSWORD_HASHER.verify(stored, _pepper_password(password))
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def needs_password_upgrade(stored: str) -> bool:
    if stored.startswith("pbkdf2_sha256$"):
        return True
    if stored.startswith("$argon2id$"):
        return PASSWORD_HASHER.check_needs_rehash(stored)
    return True


def update_password_hash(conn, user_id: str, new_hash: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE app_user
            SET password_hash = %s
            WHERE user_id = %s
            """,
            (new_hash, user_id),
        )


def verify_captcha_token(token: str | None) -> bool:
    if not token:
        return False
    if AUTH_CAPTCHA_BYPASS:
        return hmac.compare_digest(token, AUTH_CAPTCHA_BYPASS)
    return False


def get_login_attempt(conn, scope: str, scope_key: str) -> dict | None:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT scope, scope_key, fail_count, blocked_until, last_failed_at
            FROM auth_login_attempt
            WHERE scope = %s AND scope_key = %s
            """,
            (scope, scope_key),
        )
        return cur.fetchone()


def is_login_blocked(attempt: dict | None, now: datetime) -> bool:
    if not attempt:
        return False
    blocked_until = attempt.get("blocked_until")
    return bool(blocked_until and blocked_until > now)


def login_retry_after(attempt: dict | None, now: datetime) -> int:
    if not attempt:
        return 0
    blocked_until = attempt.get("blocked_until")
    if not blocked_until or blocked_until <= now:
        return 0
    return int((blocked_until - now).total_seconds())


def requires_captcha(attempt: dict | None) -> bool:
    if not attempt:
        return False
    return int(attempt.get("fail_count") or 0) >= LOGIN_CAPTCHA_THRESHOLD


def record_login_failure(conn, scope: str, scope_key: str, now: datetime) -> None:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT fail_count
            FROM auth_login_attempt
            WHERE scope = %s AND scope_key = %s
            FOR UPDATE
            """,
            (scope, scope_key),
        )
        row = cur.fetchone()
        if row:
            fail_count = int(row["fail_count"] or 0) + 1
            blocked_until = None
            if fail_count >= LOGIN_FAIL_DELAY_THRESHOLD:
                blocked_until = now + timedelta(seconds=LOGIN_FAIL_DELAY_SECONDS)
            cur.execute(
                """
                UPDATE auth_login_attempt
                SET fail_count = %s,
                    blocked_until = %s,
                    last_failed_at = %s,
                    updated_at = now()
                WHERE scope = %s AND scope_key = %s
                """,
                (fail_count, blocked_until, now, scope, scope_key),
            )
        else:
            blocked_until = None
            if 1 >= LOGIN_FAIL_DELAY_THRESHOLD:
                blocked_until = now + timedelta(seconds=LOGIN_FAIL_DELAY_SECONDS)
            cur.execute(
                """
                INSERT INTO auth_login_attempt
                  (scope, scope_key, fail_count, blocked_until, last_failed_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (scope, scope_key, 1, blocked_until, now),
            )


def clear_login_attempt(conn, scope: str, scope_key: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM auth_login_attempt
            WHERE scope = %s AND scope_key = %s
            """,
            (scope, scope_key),
        )


def create_user(conn, email: str, password: str) -> dict:
    user_id = uuid.uuid4().hex
    password_hash = hash_password(password)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO app_user (user_id, email, password_hash)
            VALUES (%s, %s, %s)
            """,
            (user_id, email, password_hash),
        )
    return {"user_id": user_id, "email": email}


def get_user_by_email(conn, email: str) -> dict | None:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT user_id, email, password_hash, created_at, last_login
            FROM app_user
            WHERE email = %s
            """,
            (email,),
        )
        return cur.fetchone()


def get_user_by_id(conn, user_id: str) -> dict | None:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT user_id, email, created_at, last_login
            FROM app_user
            WHERE user_id = %s
            """,
            (user_id,),
        )
        return cur.fetchone()


def create_session(conn, user_id: str, device_id: str | None = None) -> dict:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=SESSION_DAYS)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_session
              (session_token, user_id, device_id, created_at, expires_at, last_seen)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (token, user_id, device_id, now, expires_at, now),
        )
        cur.execute(
            """
            UPDATE app_user
            SET last_login = %s
            WHERE user_id = %s
            """,
            (now, user_id),
        )
    return {"session_token": token, "expires_at": expires_at}


def get_session(conn, token: str) -> dict | None:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT session_token, user_id, expires_at
            FROM user_session
            WHERE session_token = %s
            """,
            (token,),
        )
        return cur.fetchone()


def touch_session(conn, token: str) -> None:
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE user_session
            SET last_seen = %s
            WHERE session_token = %s
            """,
            (now, token),
        )


def revoke_session(conn, token: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM user_session
            WHERE session_token = %s
            """,
            (token,),
        )
        return cur.rowcount > 0
