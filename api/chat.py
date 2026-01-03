import json
import os
import re
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional
import time

import requests
from psycopg2.extras import RealDictCursor

from etl.utils import normalize_text

from api.search import search_verses

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
OLLAMA_TIMEOUT_SEC = float(os.getenv("OLLAMA_TIMEOUT_SEC", "20"))
EVENT_LOG_PATH = os.getenv("EVENT_LOG_PATH", "logs/events.log")
LLM_SLOW_MS = int(os.getenv("LLM_SLOW_MS", "2000"))
RETRIEVAL_SLOW_MS = int(os.getenv("RETRIEVAL_SLOW_MS", "500"))
LOG_ID_SALT = os.getenv("LOG_ID_SALT", "")

SUMMARY_MAX_CHARS = 800
SUMMARY_TRIGGER_TURNS = 30
RECENT_TURNS = 8


def select_version_id(locale: Optional[str]) -> str:
    if locale and locale.lower().startswith("ko"):
        return "krv"
    if locale:
        return "eng-web"
    return "krv"

RISK_PATTERNS = [
    r"자해",
    r"자살",
    r"죽고 싶",
    r"죽고싶",
    r"끝내고 싶",
]

CRISIS_RESPONSE = (
    "지금 많이 힘드실 것 같아요. 혼자 버티지 않으셔도 됩니다.\n"
    "한국에서는 24시간 도움을 받을 수 있는 창구가 있습니다:\n"
    "- 자살예방 상담전화 1393\n"
    "- 정신건강위기 상담전화 1577-0199\n"
    "- 긴급 상황은 112 또는 119\n"
    "가능하다면 지금 가까운 사람이나 전문가에게도 연락해 주세요."
)

TOPIC_LEXICON = {
    "anxiety": ["불안", "두려", "긴장", "초조", "걱정"],
    "sadness": ["슬프", "우울", "눈물", "상실", "외로"],
    "anger": ["분노", "화가", "짜증", "미움"],
    "guidance": ["결정", "선택", "진로", "길", "방향"],
    "forgiveness": ["죄책", "용서", "회개", "죄"],
    "relationships": ["관계", "가족", "부부", "친구", "이별"],
    "peace": ["평안", "쉼", "안식", "안정"],
}

VERSE_REQUEST_KEYWORDS = [
    "말씀",
    "성경",
    "구절",
    "verse",
    "bible",
]

PII_PATTERNS = [
    (re.compile(r"\b\d{2,3}-\d{3,4}-\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b\d{6}-\d{7}\b"), "[RRN]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{5}\b"), "[BANK]"),
]


class ConversationStore:
    def __init__(self):
        self._conversations: Dict[str, dict] = {}

    def _mem_create(
        self,
        device_id: Optional[str],
        locale: Optional[str],
        version_id: str,
        store_messages: bool,
        conversation_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> dict:
        conversation_id = conversation_id or uuid.uuid4().hex
        now = created_at or datetime.now(timezone.utc).isoformat()
        record = {
            "conversation_id": conversation_id,
            "created_at": now,
            "device_id": device_id,
            "locale": locale,
            "version_id": version_id,
            "store_messages": store_messages,
            "messages": [],
            "summary": "",
        }
        self._conversations[conversation_id] = record
        return record

    def create(
        self,
        device_id: Optional[str],
        locale: Optional[str],
        version_id: str,
        store_messages: bool = False,
        conn=None,
    ) -> dict:
        if conn is None:
            return self._mem_create(device_id, locale, version_id, store_messages)
        conversation_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_conversation
                    (conversation_id, device_id, locale, version_id, store_messages, summary, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, now(), now())
                    """,
                    (conversation_id, device_id, locale, version_id, store_messages, ""),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            return self._mem_create(device_id, locale, version_id, store_messages)
        return self._mem_create(
            device_id,
            locale,
            version_id,
            store_messages,
            conversation_id=conversation_id,
            created_at=now,
        )

    def get(self, conversation_id: str, conn=None) -> Optional[dict]:
        record = self._conversations.get(conversation_id)
        if record is not None:
            return record
        if conn is None:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT conversation_id, device_id, locale, version_id, store_messages, summary, created_at
                    FROM chat_conversation
                    WHERE conversation_id = %s
                    """,
                    (conversation_id,),
                )
                conv = cur.fetchone()
                if not conv:
                    return None
                messages = []
                if conv[4]:
                    cur.execute(
                        """
                        SELECT role, content, created_at
                        FROM chat_message
                        WHERE conversation_id = %s
                        ORDER BY created_at
                        """,
                        (conversation_id,),
                    )
                    messages = [
                        {"role": row[0], "content": row[1], "created_at": row[2].isoformat()}
                        for row in cur.fetchall()
                    ]
        except Exception:
            return self._conversations.get(conversation_id)
        record = {
            "conversation_id": conv[0],
            "device_id": conv[1],
            "locale": conv[2],
            "version_id": conv[3],
            "store_messages": conv[4],
            "summary": conv[5] or "",
            "created_at": conv[6].isoformat(),
            "messages": messages,
        }
        self._conversations[conversation_id] = record
        return record

    def delete(self, conversation_id: str, conn=None) -> bool:
        deleted = self._conversations.pop(conversation_id, None) is not None
        if conn is None:
            return deleted
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM chat_conversation WHERE conversation_id = %s",
                    (conversation_id,),
                )
                deleted = deleted or cur.rowcount > 0
            conn.commit()
            return deleted
        except Exception:
            conn.rollback()
            return deleted

    def add_message(self, conversation_id: str, role: str, content: str, conn=None) -> None:
        record = self._conversations.get(conversation_id)
        if record is None and conn is not None:
            record = self.get(conversation_id, conn=conn)
        if record is None:
            return

        record["messages"].append(
            {"role": role, "content": content, "created_at": datetime.now(timezone.utc).isoformat()}
        )
        if not record.get("store_messages", False) or conn is None:
            return

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_message (conversation_id, role, content, created_at)
                    VALUES (%s, %s, %s, now())
                    """,
                    (conversation_id, role, content),
                )
                cur.execute(
                    """
                    UPDATE chat_conversation
                    SET updated_at = now()
                    WHERE conversation_id = %s
                    """,
                    (conversation_id,),
                )
            conn.commit()
        except Exception:
            conn.rollback()

    def set_summary(self, conversation_id: str, summary: str, conn=None) -> None:
        record = self._conversations.get(conversation_id)
        if record is None and conn is not None:
            record = self.get(conversation_id, conn=conn)
        if record is None:
            return
        record["summary"] = summary
        if not record.get("store_messages", False) or conn is None:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE chat_conversation
                    SET summary = %s, updated_at = now()
                    WHERE conversation_id = %s
                    """,
                    (summary, conversation_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()


def _hash_id(value: str) -> str:
    raw = f"{LOG_ID_SALT}{value}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _mask_pii(text: str) -> str:
    masked = text
    for pattern, repl in PII_PATTERNS:
        masked = pattern.sub(repl, masked)
    return masked


def _risk_flags(text: str) -> List[str]:
    flags = []
    for pat in RISK_PATTERNS:
        if re.search(pat, text):
            flags.append("self_harm")
            break
    return flags


def _tokenize(text: str) -> List[str]:
    normalized = normalize_text(text or "")
    if not normalized:
        return []
    tokens = []
    for token in normalized.split():
        if token.isdigit():
            continue
        if len(token) < 2:
            continue
        tokens.append(token)
    return tokens


def extract_keywords(text: str, limit: int = 6) -> List[str]:
    tokens = _tokenize(text)
    counts: Dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: (-x[1], -len(x[0])))
    return [tok for tok, _ in ranked[:limit]]


def infer_topics(text: str) -> List[str]:
    found = []
    for topic, keywords in TOPIC_LEXICON.items():
        for kw in keywords:
            if kw in text:
                found.append(topic)
                break
    return found


def _explicit_verse_request(text: str) -> bool:
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in VERSE_REQUEST_KEYWORDS)


def _log_event(event_type: str, payload: dict) -> None:
    try:
        dir_path = os.path.dirname(EVENT_LOG_PATH)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        safe_payload = dict(payload or {})
        if safe_payload.get("conversation_id"):
            safe_payload["conversation_id"] = _hash_id(str(safe_payload["conversation_id"]))
        record = {
            "event_type": event_type,
            "ts": datetime.now(timezone.utc).isoformat(),
            **safe_payload,
        }
        with open(EVENT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=True) + "\n")
    except OSError:
        pass


def log_chat_event(event_type: str, payload: dict) -> None:
    _log_event(event_type, payload)


def log_verse_cited(conversation_id: str, citations: List[dict]) -> None:
    for c in citations:
        _log_event(
            "verse_cited",
            {
                "conversation_id": conversation_id,
                "version_id": c.get("version_id"),
                "book_id": c.get("book_id"),
                "chapter": c.get("chapter"),
                "verse_start": c.get("verse_start"),
                "verse_end": c.get("verse_end"),
            },
        )


def log_search_event(event_type: str, payload: dict) -> None:
    _log_event(event_type, payload)


def generate_with_ollama(prompt: str) -> Optional[str]:
    url = f"{OLLAMA_URL}/api/generate"
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    start = time.perf_counter()
    try:
        res = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT_SEC)
        res.raise_for_status()
        data = res.json()
    except requests.RequestException:
        _log_event(
            "llm_error",
            {"model": OLLAMA_MODEL, "error": "request_failed"},
        )
        return None
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    _log_event(
        "llm_latency",
        {"model": OLLAMA_MODEL, "elapsed_ms": elapsed_ms},
    )
    if elapsed_ms > LLM_SLOW_MS:
        _log_event(
            "llm_slow",
            {"model": OLLAMA_MODEL, "elapsed_ms": elapsed_ms},
        )
    return data.get("response") or None


def _extract_json(text: str) -> Optional[dict]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}")
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def gate_need_verse(user_message: str) -> dict:
    prompt = (
        "Return ONLY JSON. Decide if a Bible verse citation is needed.\n"
        f"User message: {user_message}\n"
        'Format: {"need_verse": true|false, "topics": [], "user_goal": "", "risk_flags": []}'
    )
    response = generate_with_ollama(prompt)
    data = _extract_json(response or "")
    if data and isinstance(data, dict):
        data.setdefault("risk_flags", [])
        data.setdefault("topics", [])
        data.setdefault("user_goal", "")
        data.setdefault("llm_ok", True)
        data.setdefault("source", "llm")
        if not data["topics"]:
            data["topics"] = infer_topics(user_message)
        if _explicit_verse_request(user_message):
            data["need_verse"] = True
        return data
    # Fallback rule-based gating for tests/local
    return {
        "need_verse": _explicit_verse_request(user_message),
        "topics": infer_topics(user_message),
        "user_goal": "",
        "risk_flags": [],
        "llm_ok": False,
        "source": "fallback",
    }


def summarize_messages(messages: List[dict], previous_summary: str) -> str:
    joined = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    prompt = (
        "Summarize the conversation in Korean within 800 characters. "
        "Include: user situation, emotions, repeated concerns, and preferences.\n"
        f"Previous summary:\n{previous_summary}\n\nConversation:\n{joined}\n"
    )
    response = generate_with_ollama(prompt)
    if response:
        return response.strip()[:SUMMARY_MAX_CHARS]
    # Fallback summary: last few user lines only
    user_lines = [m["content"] for m in messages if m["role"] == "user"]
    return " / ".join(user_lines[-3:])[:SUMMARY_MAX_CHARS]


def build_assistant_message(
    user_message: str, gating: dict, summary: str, recent_messages: List[dict]
) -> tuple[str, bool]:
    recent_text = "\n".join(f"{m['role']}: {m['content']}" for m in recent_messages)
    prompt = (
        "You are a gentle Korean counselor. Avoid preaching. Ask 1-2 questions. "
        "Keep it concise. Respond ONLY in Korean and do not use English.\n"
        f"Summary: {summary}\n"
        f"Recent:\n{recent_text}\n"
        f"Gating: {gating}\n"
        f"User: {user_message}\n"
    )
    response = generate_with_ollama(prompt)
    if response:
        return response.strip(), True
    return (
        "현재 상담 기능이 원활하지 않아 기본 안내만 제공하고 있습니다. "
        "불편을 드려 죄송합니다. 다른 질문이 있으신가요?",
        False,
    )


store = ConversationStore()


FALLBACK_REFERENCES = [
    {"book_id": 19, "chapter": 23, "verse": 1},
    {"book_id": 40, "chapter": 11, "verse": 28},
    {"book_id": 50, "chapter": 4, "verse": 6},
    {"book_id": 23, "chapter": 41, "verse": 10},
]


def _fallback_citations(conn, version_id: str, limit: int) -> List[dict]:
    citations = []
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        for ref in FALLBACK_REFERENCES:
            cur.execute(
                """
                SELECT v.book_id, b.ko_name AS book_name, v.chapter, v.verse, v.text
                FROM bible_verse v
                JOIN bible_book b
                  ON b.version_id = v.version_id AND b.book_id = v.book_id
                WHERE v.version_id = %s AND v.book_id = %s AND v.chapter = %s AND v.verse = %s
                """,
                (version_id, ref["book_id"], ref["chapter"], ref["verse"]),
            )
            row = cur.fetchone()
            if not row:
                continue
            citations.append(
                {
                    "version_id": version_id,
                    "book_id": row["book_id"],
                    "book_name": row["book_name"],
                    "chapter": row["chapter"],
                    "verse_start": row["verse"],
                    "verse_end": row["verse"],
                    "text": row["text"],
                }
            )
            if len(citations) >= limit:
                return citations

        cur.execute(
            """
            SELECT v.book_id, b.ko_name AS book_name, v.chapter, v.verse, v.text
            FROM bible_verse v
            JOIN bible_book b
              ON b.version_id = v.version_id AND b.book_id = v.book_id
            WHERE v.version_id = %s
            ORDER BY v.book_id, v.chapter, v.verse
            LIMIT %s
            """,
            (version_id, limit),
        )
        rows = cur.fetchall()
    for row in rows:
        citations.append(
            {
                "version_id": version_id,
                "book_id": row["book_id"],
                "book_name": row["book_name"],
                "chapter": row["chapter"],
                "verse_start": row["verse"],
                "verse_end": row["verse"],
                "text": row["text"],
            }
        )
    return citations


def retrieve_citations(conn, version_id: str, user_message: str, limit: int = 2) -> List[dict]:
    keywords = extract_keywords(user_message)
    topics = infer_topics(user_message)
    query_text = " ".join(keywords + topics) if keywords or topics else user_message

    start = time.perf_counter()
    results = search_verses(conn, version_id, query_text, limit * 3, 0)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    _log_event(
        "retrieval_latency",
        {"version_id": version_id, "elapsed_ms": elapsed_ms, "q": query_text},
    )
    if elapsed_ms > RETRIEVAL_SLOW_MS:
        _log_event(
            "retrieval_slow",
            {"version_id": version_id, "elapsed_ms": elapsed_ms, "q": query_text},
        )

    if results.get("total", 0) == 0 and query_text != user_message:
        _log_event("retrieval_zero", {"version_id": version_id, "q": query_text})
        results = search_verses(conn, version_id, user_message, limit * 3, 0)
    if results.get("total", 0) == 0:
        _log_event("retrieval_zero", {"version_id": version_id, "q": user_message})

    items = results.get("items", [])
    if keywords:
        scored = []
        for idx, item in enumerate(items):
            text_norm = normalize_text(item["text"])
            score = sum(1 for kw in keywords if kw in text_norm)
            scored.append((score, idx, item))
        scored.sort(key=lambda x: (-x[0], x[1]))
        items = [item for _, _, item in scored]

    citations = []
    seen = set()
    for item in items:
        key = (item["book_id"], item["chapter"], item["verse"])
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            {
                "version_id": version_id,
                "book_id": item["book_id"],
                "book_name": item["book_name"],
                "chapter": item["chapter"],
                "verse_start": item["verse"],
                "verse_end": item["verse"],
                "text": item["text"],
            }
        )
        if len(citations) >= limit:
            break
    if not citations:
        return _fallback_citations(conn, version_id, limit)
    return citations


def _format_citation(citation: dict) -> str:
    verse_label = (
        f"{citation['chapter']}:{citation['verse_start']}-{citation['verse_end']}"
        if citation.get("verse_end", citation["verse_start"]) > citation["verse_start"]
        else f"{citation['chapter']}:{citation['verse_start']}"
    )
    return f"({citation['book_name']} {verse_label}) {citation['text']}"


def append_citations_to_response(response: str, citations: List[dict]) -> str:
    if not citations:
        return response

    blocks = []
    for c in citations:
        blocks.append(_format_citation(c))

    citation_text = "\n\n".join(blocks)
    if citation_text in response:
        return response
    if response:
        return f"{response}\n\n{citation_text}"
    return citation_text


def _strip_citation_lines(text: str) -> str:
    if not text:
        return ""
    lines = []
    pattern = re.compile(r"^\([^)]*\d+\s*:\s*\d+(?:\s*-\s*\d+)?\)[\s\S]*$")
    for line in text.splitlines():
        if pattern.match(line.strip()):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def enforce_exact_citations(response: str, citations: List[dict]) -> tuple[str, List[dict]]:
    if not citations:
        return response, citations

    expected_blocks = [_format_citation(c) for c in citations]
    expected_text = "\n\n".join(expected_blocks)

    if expected_text in (response or ""):
        return response, citations

    stripped = _strip_citation_lines(response or "")
    if stripped:
        return f"{stripped}\n\n{expected_text}", citations
    return expected_text, citations
