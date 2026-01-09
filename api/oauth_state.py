import os
import time
from typing import Optional

import redis


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
OAUTH_STATE_TTL_SEC = int(os.getenv("OAUTH_STATE_TTL_SEC", "600"))

_REDIS_CLIENT = None
_REDIS_AVAILABLE = True
_MEM_STORE = {}


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


def _state_key(state: str) -> str:
    return f"oauth:state:{state}"


def _mem_get(key: str) -> Optional[dict]:
    data = _MEM_STORE.get(key)
    if not data:
        return None
    expires_at = int(data.get("expires_at_ts") or 0)
    if expires_at and time.time() >= expires_at:
        _MEM_STORE.pop(key, None)
        return None
    return data


def store_oauth_state(state: str, payload: dict) -> None:
    key = _state_key(state)
    ttl = max(60, OAUTH_STATE_TTL_SEC)
    client = _get_redis()
    data = dict(payload or {})
    data["expires_at_ts"] = int(time.time()) + ttl
    if client is None:
        _MEM_STORE[key] = data
        return
    client.hset(key, mapping=data)
    client.expire(key, ttl)


def consume_oauth_state(state: str) -> Optional[dict]:
    key = _state_key(state)
    client = _get_redis()
    if client is None:
        data = _mem_get(key)
        if data:
            _MEM_STORE.pop(key, None)
        return data
    pipe = client.pipeline()
    pipe.hgetall(key)
    pipe.delete(key)
    data, _deleted = pipe.execute()
    return data or None
