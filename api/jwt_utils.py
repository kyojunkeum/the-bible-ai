import hashlib
import hmac
import os
import time
import uuid
from datetime import datetime, timezone

import jwt


JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_ISSUER = os.getenv("JWT_ISSUER", "thebibleai")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "thebibleai")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TTL_SEC = int(os.getenv("JWT_ACCESS_TTL_SEC", "3600"))
JWT_REFRESH_TTL_SEC = int(os.getenv("JWT_REFRESH_TTL_SEC", "2592000"))


def _now_ts() -> int:
    return int(time.time())


def create_access_token(user_id: str, email: str | None = None) -> tuple[str, int]:
    now = _now_ts()
    exp = now + JWT_ACCESS_TTL_SEC
    payload = {
        "sub": user_id,
        "email": email,
        "typ": "access",
        "iat": now,
        "exp": exp,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, exp


def create_refresh_token(user_id: str, email: str | None = None) -> tuple[str, str, int]:
    now = _now_ts()
    exp = now + JWT_REFRESH_TTL_SEC
    refresh_id = uuid.uuid4().hex
    payload = {
        "sub": user_id,
        "email": email,
        "typ": "refresh",
        "jti": refresh_id,
        "iat": now,
        "exp": exp,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, refresh_id, exp


def _decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
        )
    except jwt.PyJWTError:
        return None


def verify_access_token(token: str) -> dict | None:
    payload = _decode_token(token)
    if not payload or payload.get("typ") != "access":
        return None
    return payload


def verify_refresh_token(token: str) -> dict | None:
    payload = _decode_token(token)
    if not payload or payload.get("typ") != "refresh":
        return None
    return payload


def hash_refresh_id(refresh_id: str) -> str:
    secret = JWT_SECRET.encode("utf-8")
    raw = refresh_id.encode("utf-8")
    return hmac.new(secret, raw, hashlib.sha256).hexdigest()


def exp_to_datetime(exp_ts: int) -> datetime:
    return datetime.fromtimestamp(exp_ts, tz=timezone.utc)
