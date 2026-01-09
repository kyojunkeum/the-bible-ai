import api.main as main_mod
from api.chat import store
from api.models import ChatMessageRequest


class FakeCursor:
    def __init__(self):
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append(str(query))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self, cursor_factory=None):
        return self._cursor

    def commit(self):
        return None

    def rollback(self):
        return None


def _prepare(monkeypatch, store_messages: bool):
    record = store.create(device_id="test", locale="ko-KR", version_id="krv", store_messages=True)
    conversation_id = record["conversation_id"]
    cursor = FakeCursor()
    conn = FakeConn(cursor)

    monkeypatch.setattr(
        main_mod,
        "get_conversation_meta",
        lambda _cid: {
            "mode": "authenticated",
            "store_messages": store_messages,
            "expires_at": None,
            "turn_limit": 10,
            "turn_count": 0,
        },
    )
    monkeypatch.setattr(
        main_mod,
        "enforce_turn_and_increment",
        lambda _cid: {
            "status": "ok",
            "turn_count": 1,
            "turn_limit": 10,
            "expires_at": None,
        },
    )
    monkeypatch.setattr(
        main_mod,
        "gate_need_verse",
        lambda *_args, **_kwargs: {
            "need_verse": False,
            "topics": [],
            "user_goal": "",
            "risk_flags": [],
            "llm_ok": True,
            "source": "test",
            "trigger_reason": [],
            "exclude_reason": [],
        },
    )
    monkeypatch.setattr(main_mod, "build_assistant_message", lambda *_args, **_kwargs: ("테스트 응답", True))
    monkeypatch.setattr(main_mod, "_verify_citations", lambda _conn, citations: citations)
    return conversation_id, conn, cursor


def _chat_insert_count(cursor: FakeCursor) -> int:
    return sum("INSERT INTO chat_message" in query for query in cursor.queries)


def test_store_messages_false_skips_db_insert(monkeypatch):
    conversation_id, conn, cursor = _prepare(monkeypatch, store_messages=False)
    payload = ChatMessageRequest(user_message="테스트 메시지", client_context=None)
    main_mod.post_message(conversation_id, payload, conn=conn)

    assert _chat_insert_count(cursor) == 0
    store.delete(conversation_id)


def test_store_messages_true_writes_db_insert(monkeypatch):
    conversation_id, conn, cursor = _prepare(monkeypatch, store_messages=True)
    payload = ChatMessageRequest(user_message="테스트 메시지", client_context=None)
    main_mod.post_message(conversation_id, payload, conn=conn)

    assert _chat_insert_count(cursor) >= 1
    store.delete(conversation_id)


def test_anonymous_daily_limit_blocks(monkeypatch):
    record = store.create(device_id="device-1", locale="ko-KR", version_id="krv", store_messages=False)
    conversation_id = record["conversation_id"]
    cursor = FakeCursor()
    conn = FakeConn(cursor)

    monkeypatch.setattr(
        main_mod,
        "get_conversation_meta",
        lambda _cid: {
            "mode": "anonymous",
            "store_messages": False,
            "expires_at": None,
            "turn_limit": 10,
            "turn_count": 0,
        },
    )
    monkeypatch.setattr(
        main_mod,
        "enforce_anonymous_daily_limit",
        lambda *_args, **_kwargs: {"status": "limit", "count": 11, "limit": 10},
    )
    payload = ChatMessageRequest(user_message="테스트 메시지", client_context=None)
    try:
        main_mod.post_message(conversation_id, payload, conn=conn)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 429
    else:
        raise AssertionError("expected daily limit enforcement")
    store.delete(conversation_id)
