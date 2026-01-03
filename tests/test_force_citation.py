from api.chat import store
from api.models import ChatMessageRequest
import api.chat as chat_mod
import api.main as main_mod


class FakeCursor:
    def __init__(self, data_by_key):
        self._data = data_by_key
        self._row = None
        self._rows = []

    def execute(self, query, params):
        if "WHERE v.version_id = %s AND v.book_id = %s AND v.chapter = %s AND v.verse = %s" in query:
            key = (params[1], params[2], params[3])
            self._row = self._data.get(key)
            self._rows = []
            return
        if "ORDER BY v.book_id, v.chapter, v.verse" in query:
            self._rows = list(self._data.values())
            self._row = None
            return
        self._row = None
        self._rows = []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self, cursor_factory=None):
        return self._cursor


def test_force_citation_on_fifth_turn(monkeypatch):
    record = store.create(device_id="test", locale="ko-KR", version_id="krv", store_messages=False)
    conversation_id = record["conversation_id"]

    for idx in range(4):
        store.add_message(conversation_id, "assistant", f"a{idx}")
        store.add_message(conversation_id, "user", f"u{idx}")

    monkeypatch.setattr(
        main_mod,
        "gate_need_verse",
        lambda _msg: {
            "need_verse": False,
            "topics": [],
            "user_goal": "",
            "risk_flags": [],
            "llm_ok": True,
            "source": "test",
        },
    )
    monkeypatch.setattr(main_mod, "build_assistant_message", lambda *_args, **_kw: ("테스트 응답", True))
    monkeypatch.setattr(main_mod, "_verify_citations", lambda _conn, citations: citations)
    monkeypatch.setattr(
        chat_mod,
        "search_verses",
        lambda _conn, _version_id, _query, _limit, _offset: {"total": 0, "items": []},
    )

    data_by_key = {
        (19, 23, 1): {
            "book_id": 19,
            "book_name": "시편",
            "chapter": 23,
            "verse": 1,
            "text": "여호와는 나의 목자시니 내게 부족함이 없으리로다",
        },
        (40, 11, 28): {
            "book_id": 40,
            "book_name": "마태복음",
            "chapter": 11,
            "verse": 28,
            "text": "수고하고 무거운 짐 진 자들아 다 내게로 오라 내가 너희를 쉬게 하리라",
        },
    }
    conn = FakeConn(FakeCursor(data_by_key))

    payload = ChatMessageRequest(user_message="테스트입니다", client_context=None)
    response = main_mod.post_message(conversation_id, payload, conn=conn)

    assert response["memory"]["gating"]["need_verse"] is True
    assert response["citations"]
    assert "시편" in response["assistant_message"] or "마태복음" in response["assistant_message"]
