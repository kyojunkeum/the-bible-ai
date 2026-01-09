import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import redis


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ANON_CHAT_TTL_SEC = int(os.getenv("ANON_CHAT_TTL_SEC", "7200"))
ANON_CHAT_TURN_LIMIT = int(os.getenv("ANON_CHAT_TURN_LIMIT", "10"))
ANON_DAILY_TURN_LIMIT = int(os.getenv("ANON_DAILY_TURN_LIMIT", "10"))
KST_TZ = timezone(timedelta(hours=9))

_REDIS_CLIENT = None
_REDIS_AVAILABLE = True
_MEM_STORE = {}
_MEM_DAILY = {}


def _get_redis():
    global _REDIS_CLIENT, _REDIS_AVAILABLE
    if not _REDIS_AVAILABLE:
        return None
    if _REDIS_CLIENT is None:
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        try:
            client.ping()
        except redis.RedisError:
            _REDIS_AVAILABLE = False
            return None
        _REDIS_CLIENT = client
    return _REDIS_CLIENT


def _meta_key(conversation_id: str) -> str:
    return f"chat:meta:{conversation_id}"


def _to_bool(value: Optional[str]) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "y"}


def _iso_from_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _mem_get(key: str) -> Optional[dict]:
    data = _MEM_STORE.get(key)
    if not data:
        return None
    expires_ts = int(data.get("expires_at_ts") or 0)
    if expires_ts and time.time() >= expires_ts:
        _MEM_STORE.pop(key, None)
        return None
    return data


def _daily_key(scope: str, identifier: str, date_key: str) -> str:
    return f"chat:anon:daily:{scope}:{identifier}:{date_key}"


def _kst_date_key(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(KST_TZ)
    return now.strftime("%Y%m%d")


def _seconds_until_kst_day_end(now: Optional[datetime] = None) -> int:
    now = now or datetime.now(KST_TZ)
    next_midnight = datetime.combine(
        now.date() + timedelta(days=1),
        datetime.min.time(),
        tzinfo=KST_TZ,
    )
    return max(int((next_midnight - now).total_seconds()), 60)


def _mem_daily_get(key: str) -> Optional[dict]:
    data = _MEM_DAILY.get(key)
    if not data:
        return None
    expires_ts = int(data.get("expires_at_ts") or 0)
    if expires_ts and time.time() >= expires_ts:
        _MEM_DAILY.pop(key, None)
        return None
    return data


def init_conversation_meta(
    conversation_id: str,
    mode: str,
    store_messages: bool,
    expires_at: Optional[datetime],
    turn_limit: int,
    turn_count: int = 0,
    user_id: Optional[str] = None,
    locale: Optional[str] = None,
    version_id: Optional[str] = None,
) -> dict:
    client = _get_redis()
    key = _meta_key(conversation_id)
    expires_ts = int(expires_at.timestamp()) if expires_at else 0
    payload = {
        "mode": mode,
        "store_messages": "1" if store_messages else "0",
        "expires_at_ts": str(expires_ts),
        "turn_limit": str(int(turn_limit or 0)),
        "turn_count": str(int(turn_count or 0)),
    }
    if user_id:
        payload["user_id"] = user_id
    if locale:
        payload["locale"] = locale
    if version_id:
        payload["version_id"] = version_id
    if client is None:
        _MEM_STORE[key] = dict(payload)
    else:
        pipe = client.pipeline()
        pipe.hset(key, mapping=payload)
        if expires_ts:
            pipe.expireat(key, expires_ts)
        pipe.execute()
    return {
        "mode": mode,
        "store_messages": store_messages,
        "expires_at": _iso_from_ts(expires_ts) if expires_ts else None,
        "turn_limit": int(turn_limit or 0),
        "turn_count": int(turn_count or 0),
    }


def get_conversation_meta(conversation_id: str) -> Optional[dict]:
    client = _get_redis()
    key = _meta_key(conversation_id)
    data = _mem_get(key) if client is None else client.hgetall(key)
    if not data:
        return None
    expires_ts = int(data.get("expires_at_ts") or 0)
    return {
        "mode": data.get("mode") or "anonymous",
        "store_messages": _to_bool(data.get("store_messages")),
        "expires_at": _iso_from_ts(expires_ts) if expires_ts else None,
        "turn_limit": int(data.get("turn_limit") or 0),
        "turn_count": int(data.get("turn_count") or 0),
        "user_id": data.get("user_id"),
        "locale": data.get("locale"),
        "version_id": data.get("version_id"),
    }


_TURN_CHECK_LUA = """
local key = KEYS[1]
if redis.call("EXISTS", key) == 0 then
  return {0, "not_found"}
end
local expires_at = tonumber(redis.call("HGET", key, "expires_at_ts") or "0")
local now = tonumber(ARGV[1])
if expires_at > 0 and now >= expires_at then
  return {0, "expired", expires_at}
end
local turn_limit = tonumber(redis.call("HGET", key, "turn_limit") or "0")
local turn_count = tonumber(redis.call("HGET", key, "turn_count") or "0")
if turn_limit > 0 and turn_count >= turn_limit then
  return {turn_count, "limit", turn_limit}
end
local new_count = redis.call("HINCRBY", key, "turn_count", 1)
return {new_count, "ok", turn_limit, expires_at}
"""

_DAILY_LIMIT_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local new_count = redis.call("INCR", key)
if new_count == 1 then
  redis.call("EXPIRE", key, ttl)
end
if new_count > limit then
  return {new_count, "limit"}
end
return {new_count, "ok"}
"""


def enforce_turn_and_increment(conversation_id: str) -> dict:
    client = _get_redis()
    key = _meta_key(conversation_id)
    now_ts = int(time.time())
    if client is None:
        data = _mem_get(key)
        if not data:
            return {"status": "not_found"}
        expires_ts = int(data.get("expires_at_ts") or 0)
        if expires_ts and now_ts >= expires_ts:
            _MEM_STORE.pop(key, None)
            return {
                "status": "expired",
                "expires_at": _iso_from_ts(expires_ts),
            }
        turn_limit = int(data.get("turn_limit") or 0)
        turn_count = int(data.get("turn_count") or 0)
        if turn_limit > 0 and turn_count >= turn_limit:
            return {
                "status": "limit",
                "turn_count": turn_count,
                "turn_limit": turn_limit,
            }
        turn_count += 1
        data["turn_count"] = str(turn_count)
        return {
            "status": "ok",
            "turn_count": turn_count,
            "turn_limit": turn_limit,
            "expires_at": _iso_from_ts(expires_ts) if expires_ts else None,
        }
    result = client.eval(_TURN_CHECK_LUA, 1, key, now_ts)
    if not result:
        return {"status": "not_found"}
    status = result[1]
    if status == "ok":
        return {
            "status": "ok",
            "turn_count": int(result[0]),
            "turn_limit": int(result[2] or 0),
            "expires_at": _iso_from_ts(int(result[3])) if int(result[3] or 0) else None,
        }
    if status == "expired":
        return {
            "status": "expired",
            "expires_at": _iso_from_ts(int(result[2])) if int(result[2] or 0) else None,
        }
    if status == "limit":
        return {
            "status": "limit",
            "turn_count": int(result[0]),
            "turn_limit": int(result[2] or 0),
        }
    return {"status": "not_found"}


def build_anonymous_meta_ttl() -> tuple[datetime, int]:
    ttl_sec = max(60, ANON_CHAT_TTL_SEC)
    return datetime.now(timezone.utc) + timedelta(seconds=ttl_sec), ttl_sec


def enforce_anonymous_daily_limit(
    identifier: str,
    limit: int | None = None,
    scope: str = "device",
) -> dict:
    if not identifier:
        return {"status": "ok"}
    limit = int(limit or ANON_DAILY_TURN_LIMIT)
    now = datetime.now(KST_TZ)
    date_key = _kst_date_key(now)
    ttl = _seconds_until_kst_day_end(now)
    key = _daily_key(scope, identifier, date_key)
    client = _get_redis()
    if client is None:
        data = _mem_daily_get(key)
        if not data:
            data = {"count": 0, "expires_at_ts": int(time.time()) + ttl}
            _MEM_DAILY[key] = data
        data["count"] = int(data.get("count") or 0) + 1
        if data["count"] > limit:
            return {"status": "limit", "count": data["count"], "limit": limit}
        return {"status": "ok", "count": data["count"], "limit": limit}
    result = client.eval(_DAILY_LIMIT_LUA, 1, key, limit, ttl)
    if not result:
        return {"status": "ok"}
    status = result[1]
    if status == "limit":
        return {"status": "limit", "count": int(result[0]), "limit": limit}
    return {"status": "ok", "count": int(result[0]), "limit": limit}


def get_anonymous_daily_usage(
    identifier: str,
    limit: int | None = None,
    scope: str = "device",
) -> dict:
    if not identifier:
        limit = int(limit or ANON_DAILY_TURN_LIMIT)
        return {"count": 0, "limit": limit, "remaining": limit}
    limit = int(limit or ANON_DAILY_TURN_LIMIT)
    now = datetime.now(KST_TZ)
    date_key = _kst_date_key(now)
    key = _daily_key(scope, identifier, date_key)
    client = _get_redis()
    if client is None:
        data = _mem_daily_get(key)
        count = int(data.get("count") or 0) if data else 0
        remaining = max(limit - count, 0)
        return {"count": count, "limit": limit, "remaining": remaining}
    raw = client.get(key)
    count = int(raw or 0)
    remaining = max(limit - count, 0)
    return {"count": count, "limit": limit, "remaining": remaining}
