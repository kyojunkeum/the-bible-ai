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

from api.search import TRGM_SIMILARITY_THRESHOLD, search_verses, search_verses_vector

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
OLLAMA_TIMEOUT_SEC = float(os.getenv("OLLAMA_TIMEOUT_SEC", "60"))
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
EMBEDDING_TIMEOUT_SEC = float(os.getenv("EMBEDDING_TIMEOUT_SEC", "5"))
EVENT_LOG_PATH = os.getenv("EVENT_LOG_PATH", "logs/events.log")
LLM_SLOW_MS = int(os.getenv("LLM_SLOW_MS", "2000"))
RETRIEVAL_SLOW_MS = int(os.getenv("RETRIEVAL_SLOW_MS", "500"))
LOG_ID_SALT = os.getenv("LOG_ID_SALT", "")
ENABLE_MORPH_ANALYZER = os.getenv("ENABLE_MORPH_ANALYZER", "1") == "1"
MAX_QUERY_TERMS = int(os.getenv("MAX_QUERY_TERMS", "20"))
VECTOR_ENABLED = os.getenv("VECTOR_ENABLED", "1") == "1"
VECTOR_TOPK = int(os.getenv("VECTOR_TOPK", "50"))
VECTOR_WINDOW_SIZE = int(os.getenv("VECTOR_WINDOW_SIZE", "5"))
RERANK_MODE = "ko-bert"
RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "30"))
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "3"))
KOBERT_MODEL_ID = os.getenv("KOBERT_MODEL_ID", "skt/kobert-base-v1")
MIN_CITATION_RANK = float(os.getenv("MIN_CITATION_RANK", "0.05"))
MIN_CITATION_TRGM = float(os.getenv("MIN_CITATION_TRGM", str(TRGM_SIMILARITY_THRESHOLD)))
MIN_CITATION_KEYWORD_HITS = int(os.getenv("MIN_CITATION_KEYWORD_HITS", "1"))

SUMMARY_MAX_CHARS = 800
SUMMARY_TRIGGER_TURNS = 30
RECENT_TURNS = 8


def select_version_id(locale: Optional[str]) -> str:
    if locale and locale.lower().startswith("ko"):
        return "krv"
    if locale:
        return "eng-web"
    return "krv"


LANG_KO_RE = re.compile(r"[가-힣]")
LANG_OTHER_RE = re.compile(r"[A-Za-z\u3040-\u30ff\u3400-\u9fff]")


def select_citation_version_id(locale: Optional[str], text: str) -> str:
    if text and LANG_KO_RE.search(text):
        return "krv"
    if text and LANG_OTHER_RE.search(text):
        return "eng-web"
    return select_version_id(locale)

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

SYNONYM_MAP = {
    "불안": ["근심", "염려", "걱정"],
    "두려": ["무서움", "공포"],
    "슬프": ["우울", "비통", "눈물"],
    "상실": ["이별", "잃음"],
    "분노": ["화", "격분"],
    "죄책": ["책망", "정죄"],
    "용서": ["용납", "사함"],
    "관계": ["갈등", "다툼"],
    "평안": ["안식", "쉼", "안정"],
}

CLOSING_KEYWORDS = [
    "정리",
    "마무리",
    "결론",
    "기도",
    "기도해",
    "정돈",
]

INFO_QUESTION_KEYWORDS = [
    "뜻",
    "의미",
    "정의",
    "설명",
    "알려줘",
    "정보",
    "무엇",
    "뭐",
    "어떤",
]

SMALL_TALK_KEYWORDS = [
    "안녕",
    "고마워",
    "감사",
    "잘 지내",
    "좋아",
    "오케이",
    "ok",
    "thanks",
]

SMALL_TALK_PATTERN = re.compile(r"(ㅋ{2,}|ㅎ{2,})")

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
        mode: str = "anonymous",
        expires_at: Optional[str] = None,
        turn_limit: int = 0,
        turn_count: int = 0,
        user_id: Optional[str] = None,
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
            "mode": mode,
            "expires_at": expires_at,
            "turn_limit": turn_limit,
            "turn_count": turn_count,
            "user_id": user_id,
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
        mode: str = "anonymous",
        expires_at: Optional[str] = None,
        turn_limit: int = 0,
        turn_count: int = 0,
        user_id: Optional[str] = None,
    ) -> dict:
        if conn is None:
            return self._mem_create(
                device_id,
                locale,
                version_id,
                store_messages,
                mode=mode,
                expires_at=expires_at,
                turn_limit=turn_limit,
                turn_count=turn_count,
                user_id=user_id,
            )
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
            return self._mem_create(
                device_id,
                locale,
                version_id,
                store_messages,
                mode=mode,
                expires_at=expires_at,
                turn_limit=turn_limit,
                turn_count=turn_count,
                user_id=user_id,
            )
        return self._mem_create(
            device_id,
            locale,
            version_id,
            store_messages,
            conversation_id=conversation_id,
            created_at=now,
            mode=mode,
            expires_at=expires_at,
            turn_limit=turn_limit,
            turn_count=turn_count,
            user_id=user_id,
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
            "mode": None,
            "expires_at": None,
            "turn_limit": None,
            "turn_count": None,
            "user_id": None,
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


KIWI = None
KIWI_ERROR = False
KIWI_POS_TAGS = {"NNG", "NNP", "NNB", "VV", "VA", "VX"}
KOBERT_TOKENIZER = None
KOBERT_MODEL = None
KOBERT_ERROR = False


def _get_kiwi():
    global KIWI, KIWI_ERROR
    if not ENABLE_MORPH_ANALYZER or KIWI_ERROR:
        return None
    if KIWI is None:
        try:
            from kiwipiepy import Kiwi

            KIWI = Kiwi()
        except Exception:
            KIWI_ERROR = True
            return None
    return KIWI


def _get_kobert():
    global KOBERT_TOKENIZER, KOBERT_MODEL, KOBERT_ERROR
    if KOBERT_ERROR:
        return None, None
    if KOBERT_MODEL is None or KOBERT_TOKENIZER is None:
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer

            KOBERT_TOKENIZER = AutoTokenizer.from_pretrained(KOBERT_MODEL_ID)
            KOBERT_MODEL = AutoModel.from_pretrained(KOBERT_MODEL_ID)
            KOBERT_MODEL.eval()
            KOBERT_MODEL.to(torch.device("cpu"))
        except Exception:
            KOBERT_ERROR = True
            return None, None
    return KOBERT_TOKENIZER, KOBERT_MODEL


def _embed_text(text: str) -> Optional[List[float]]:
    if not text:
        return None
    payload = {"model": OLLAMA_EMBED_MODEL, "prompt": text}
    start = time.perf_counter()
    try:
        res = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json=payload,
            timeout=EMBEDDING_TIMEOUT_SEC,
        )
        res.raise_for_status()
        data = res.json()
    except requests.RequestException:
        _log_event(
            "embedding_error",
            {"model": OLLAMA_EMBED_MODEL, "error": "request_failed"},
        )
        return None
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    _log_event(
        "embedding_latency",
        {"model": OLLAMA_EMBED_MODEL, "elapsed_ms": elapsed_ms},
    )
    embedding = data.get("embedding")
    if not isinstance(embedding, list):
        return None
    if EMBEDDING_DIM and len(embedding) != EMBEDDING_DIM:
        _log_event(
            "embedding_error",
            {
                "model": OLLAMA_EMBED_MODEL,
                "error": "dimension_mismatch",
                "expected": EMBEDDING_DIM,
                "actual": len(embedding),
            },
        )
        return None
    return embedding


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


def _tokenize_morph(text: str) -> List[str]:
    normalized = normalize_text(text or "")
    if not normalized:
        return []
    if not re.search(r"[가-힣]", normalized):
        return _tokenize(normalized)
    kiwi = _get_kiwi()
    if not kiwi:
        return _tokenize(normalized)
    try:
        tokens = kiwi.tokenize(normalized)
    except Exception:
        return _tokenize(normalized)
    results = []
    for token in tokens:
        if token.tag not in KIWI_POS_TAGS:
            continue
        term = token.form
        if term.isdigit() or len(term) < 2:
            continue
        results.append(term)
    return results


def extract_keywords(text: str, limit: int = 6) -> List[str]:
    return extract_keywords_from_texts([text], limit=limit)


def extract_keywords_from_texts(texts: List[str], limit: int = 6) -> List[str]:
    counts: Dict[str, int] = {}
    for text in texts:
        tokens = _tokenize_morph(text)
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


def _expand_topics_to_terms(topics: List[str]) -> List[str]:
    terms = []
    for topic in topics:
        terms.extend(TOPIC_LEXICON.get(topic, []))
    seen = set()
    deduped = []
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        deduped.append(term)
    return deduped


def _fetch_synonyms_from_db(conn, terms: List[str]) -> Dict[str, List[str]]:
    if conn is None or not terms:
        return {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT term, synonym
                FROM search_synonym
                WHERE term = ANY(%s)
                """,
                (terms,),
            )
            rows = cur.fetchall()
    except Exception:
        return {}
    synonyms: Dict[str, List[str]] = {}
    for term, synonym in rows:
        synonyms.setdefault(term, []).append(synonym)
    return synonyms


def _expand_synonyms(conn, terms: List[str], limit_per_term: int = 3) -> List[str]:
    db_synonyms = _fetch_synonyms_from_db(conn, terms)
    seen = set(terms)
    expanded: List[str] = []
    for term in terms:
        candidates = db_synonyms.get(term, []) + SYNONYM_MAP.get(term, [])
        added = 0
        for candidate in candidates:
            if candidate in seen or len(candidate) < 2:
                continue
            seen.add(candidate)
            expanded.append(candidate)
            added += 1
            if added >= limit_per_term:
                break
    return expanded


def _dedupe_terms(terms: List[str]) -> List[str]:
    seen = set()
    deduped = []
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        deduped.append(term)
    return deduped


def _passes_min_relevance(item: dict, score_terms: List[str]) -> bool:
    keyword_hits = int(item.get("keyword_hits") or 0)
    rank = float(item.get("rank") or 0.0)
    trgm_sim = float(item.get("trgm_sim") or 0.0)
    if score_terms and keyword_hits >= MIN_CITATION_KEYWORD_HITS:
        return True
    if rank >= MIN_CITATION_RANK:
        return True
    if trgm_sim >= MIN_CITATION_TRGM:
        return True
    return False


def _merge_candidates(fts_items: List[dict], vector_items: List[dict]) -> List[dict]:
    merged: Dict[tuple, dict] = {}
    for item in fts_items:
        key = (item["book_id"], item["chapter"], item["verse"])
        merged[key] = dict(item)
        merged[key]["source"] = "fts"
    for item in vector_items:
        key = (item["book_id"], item["chapter"], item["verse"])
        if key in merged:
            merged[key]["vector_distance"] = item.get("vector_distance")
            merged[key]["source"] = "hybrid"
        else:
            merged[key] = dict(item)
    return list(merged.values())


def _candidate_key(item: dict) -> str:
    return f"{item['book_id']}:{item['chapter']}:{item['verse']}"


def _candidate_order(items: List[dict], limit: int = 10) -> List[str]:
    return [_candidate_key(item) for item in items[:limit]]


def _rerank_delta(before: List[str], after: List[str]) -> List[dict]:
    before_pos = {key: idx for idx, key in enumerate(before)}
    after_pos = {key: idx for idx, key in enumerate(after)}
    deltas = []
    for key in after:
        if key in before_pos and before_pos[key] != after_pos[key]:
            deltas.append({"key": key, "from": before_pos[key], "to": after_pos[key]})
    return deltas


def _recent_user_texts(recent_messages: Optional[List[dict]], limit: int = 3) -> List[str]:
    if not recent_messages:
        return []
    user_texts = [m.get("content", "") for m in recent_messages if m.get("role") == "user"]
    return [text for text in user_texts[-limit:] if text]


def _build_context_text(user_message: str, summary: str, recent_messages: Optional[List[dict]]) -> str:
    parts = [user_message]
    recent_texts = _recent_user_texts(recent_messages)
    if recent_texts and recent_texts[-1] == user_message:
        recent_texts = recent_texts[:-1]
    parts.extend(recent_texts)
    if summary:
        parts.append(summary)
    return " ".join(part for part in parts if part)


def _is_info_request(text: str, topics: List[str]) -> bool:
    if not text:
        return False
    if topics:
        return False
    if any(keyword in text for keyword in CLOSING_KEYWORDS):
        return False
    if _explicit_verse_request(text):
        return False
    lowered = text.lower()
    if any(keyword in lowered for keyword in INFO_QUESTION_KEYWORDS):
        return True
    if "?" in text and not _explicit_verse_request(text):
        return True
    return False


def _is_small_talk(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    if any(keyword in text for keyword in CLOSING_KEYWORDS):
        return False
    if _explicit_verse_request(text):
        return False
    if SMALL_TALK_PATTERN.search(text):
        return True
    if any(keyword in lowered for keyword in SMALL_TALK_KEYWORDS):
        return True
    return False


def _rule_based_gating(
    user_message: str, summary: str, recent_messages: Optional[List[dict]]
) -> dict:
    context_text = _build_context_text(user_message, summary, recent_messages)
    topics = infer_topics(context_text)
    explicit_request = _explicit_verse_request(user_message) or _explicit_verse_request(context_text)
    closing_stage = any(keyword in context_text for keyword in CLOSING_KEYWORDS)
    info_request = _is_info_request(user_message, topics)
    small_talk = _is_small_talk(user_message)

    trigger_reason = []
    if explicit_request:
        trigger_reason.append("explicit_request")
    if topics:
        trigger_reason.append("strong_emotion")
    if closing_stage:
        trigger_reason.append("closing_stage")

    exclude_reason = []
    if info_request:
        exclude_reason.append("info_request")
    if small_talk:
        exclude_reason.append("small_talk")

    if explicit_request:
        need_verse = True
    elif info_request or small_talk:
        need_verse = False
    elif topics or closing_stage:
        need_verse = True
    else:
        need_verse = None

    return {
        "need_verse": need_verse,
        "topics": topics,
        "trigger_reason": trigger_reason,
        "exclude_reason": exclude_reason,
    }


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


def _rerank_with_llm(context_text: str, candidates: List[dict]) -> Optional[List[dict]]:
    if not candidates:
        return None
    limited = candidates[:RERANK_CANDIDATES]
    lines = []
    for idx, item in enumerate(limited, start=1):
        verse_label = f"{item['book_name']} {item['chapter']}:{item['verse']}"
        lines.append(f"{idx}. ({verse_label}) {item['text']}")
    prompt = (
        "Return ONLY JSON. Rank candidate Bible verses by relevance to the counseling context.\n"
        f"Context: {context_text}\n"
        "Candidates:\n"
        + "\n".join(lines)
        + "\nFormat: {\"scores\":[{\"index\":1,\"score\":0.87}]}\n"
        "Score range: 0 to 1. Include all candidates."
    )
    response = generate_with_ollama(prompt)
    data = _extract_json(response or "")
    if not data or "scores" not in data:
        return None
    scores = {}
    for item in data.get("scores", []):
        try:
            idx = int(item.get("index"))
            score = float(item.get("score"))
        except (TypeError, ValueError):
            continue
        if 1 <= idx <= len(limited):
            scores[idx - 1] = score
    if not scores:
        return None
    reranked = []
    for idx, item in enumerate(limited):
        score = scores.get(idx, 0.0)
        enriched = dict(item)
        enriched["rerank_score"] = score
        reranked.append(enriched)
    reranked.sort(key=lambda x: (-x.get("rerank_score", 0.0), x.get("vector_distance", 9999.0)))
    return reranked + candidates[len(limited) :]


def _rerank_with_kobert(context_text: str, candidates: List[dict]) -> Optional[List[dict]]:
    tokenizer, model = _get_kobert()
    if not tokenizer or not model or not candidates:
        return None
    try:
        import torch
        from torch.nn.functional import cosine_similarity
    except Exception:
        return None
    limited = candidates[:RERANK_CANDIDATES]
    with torch.no_grad():
        ctx = tokenizer(context_text, return_tensors="pt", truncation=True, max_length=256)
        ctx_out = model(**ctx)
        ctx_vec = ctx_out.last_hidden_state[:, 0]
        reranked = []
        for item in limited:
            inputs = tokenizer(item["text"], return_tensors="pt", truncation=True, max_length=256)
            outputs = model(**inputs)
            vec = outputs.last_hidden_state[:, 0]
            score = float(cosine_similarity(ctx_vec, vec).item())
            enriched = dict(item)
            enriched["rerank_score"] = score
            reranked.append(enriched)
    reranked.sort(key=lambda x: (-x.get("rerank_score", 0.0), x.get("vector_distance", 9999.0)))
    return reranked + candidates[len(limited) :]


def _rerank_candidates(context_text: str, candidates: List[dict]) -> List[dict]:
    if not candidates:
        return candidates
    mode = (RERANK_MODE or "ko-bert").lower()
    if mode == "ko-bert":
        reranked = _rerank_with_kobert(context_text, candidates)
        if reranked:
            return reranked
    return candidates


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


def gate_need_verse(
    user_message: str, summary: str = "", recent_messages: Optional[List[dict]] = None
) -> dict:
    context_text = _build_context_text(user_message, summary, recent_messages)
    prompt = (
        "Return ONLY JSON. Decide if a Bible verse citation is needed.\n"
        f"Summary: {summary}\n"
        f"Recent: {context_text}\n"
        f"User message: {user_message}\n"
        'Format: {"need_verse": true|false, "topics": [], "user_goal": "", "risk_flags": []}'
    )
    response = generate_with_ollama(prompt)
    data = _extract_json(response or "")
    rule = _rule_based_gating(user_message, summary, recent_messages)
    if data and isinstance(data, dict):
        data.setdefault("risk_flags", [])
        data.setdefault("topics", [])
        data.setdefault("user_goal", "")
        data.setdefault("llm_ok", True)
        data.setdefault("source", "llm")
        data["topics"] = list(dict.fromkeys(data["topics"] + rule["topics"]))
        if rule["need_verse"] is not None:
            data["need_verse"] = rule["need_verse"]
            data["source"] = "rule"
        data["trigger_reason"] = rule["trigger_reason"]
        data["exclude_reason"] = rule["exclude_reason"]
        return data
    # Fallback rule-based gating for tests/local
    return {
        "need_verse": rule["need_verse"] or False,
        "topics": rule["topics"],
        "user_goal": "",
        "risk_flags": [],
        "llm_ok": False,
        "source": "rule",
        "trigger_reason": rule["trigger_reason"],
        "exclude_reason": rule["exclude_reason"],
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


def retrieve_citations(
    conn,
    version_id: str,
    user_message: str,
    summary: str = "",
    recent_messages: Optional[List[dict]] = None,
    limit: int = 2,
) -> tuple[List[dict], dict]:
    context_text = _build_context_text(user_message, summary, recent_messages)
    recent_texts = _recent_user_texts(recent_messages)
    if recent_texts and recent_texts[-1] == user_message:
        recent_texts = recent_texts[:-1]
    keyword_sources = [user_message] + recent_texts + ([summary] if summary else [])
    keywords = extract_keywords_from_texts(keyword_sources, limit=8)
    topics = infer_topics(context_text)
    topic_terms = _expand_topics_to_terms(topics)
    primary_terms = _dedupe_terms(keywords + topic_terms)
    primary_terms = primary_terms[:MAX_QUERY_TERMS]
    synonyms = _expand_synonyms(conn, primary_terms)
    synonyms = synonyms[: max(0, MAX_QUERY_TERMS - len(primary_terms))]
    query_text = " ".join(primary_terms) if primary_terms else user_message
    selection_reason = "fts_rank"
    if keywords:
        selection_reason = "keyword_overlap"
    elif synonyms:
        selection_reason = "synonym_overlap"
    meta = {
        "query_text": query_text,
        "keywords": keywords,
        "topics": topics,
        "synonyms": synonyms,
        "morph_enabled": _get_kiwi() is not None,
        "vector_enabled": VECTOR_ENABLED,
        "vector_window_size": VECTOR_WINDOW_SIZE,
        "vector_topk": VECTOR_TOPK,
        "candidates": [],
        "selection_reason": selection_reason,
        "total_candidates": 0,
        "failure_reason": "",
    }

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

    vector_items: List[dict] = []

    if results.get("total", 0) == 0 and synonyms:
        _log_event("retrieval_zero", {"version_id": version_id, "q": query_text})
        synonym_query = " ".join(synonyms)
        results = search_verses(conn, version_id, synonym_query, limit * 3, 0)
        meta["query_text_original"] = query_text
        meta["query_text"] = synonym_query
    if results.get("total", 0) == 0 and query_text != user_message:
        _log_event("retrieval_zero", {"version_id": version_id, "q": meta["query_text"]})
        results = search_verses(conn, version_id, user_message, limit * 3, 0)
        meta["query_text_original"] = meta["query_text"]
        meta["query_text"] = user_message
    if results.get("total", 0) == 0:
        _log_event("retrieval_zero", {"version_id": version_id, "q": user_message})

    fts_items = results.get("items", [])
    meta["fts_candidates"] = len(fts_items)
    if VECTOR_ENABLED and meta["fts_candidates"] > 0:
        embed = _embed_text(context_text)
        if embed:
            vec_start = time.perf_counter()
            vector_items = search_verses_vector(
                conn, version_id, embed, VECTOR_TOPK, VECTOR_WINDOW_SIZE
            )
            vec_elapsed_ms = int((time.perf_counter() - vec_start) * 1000)
            _log_event(
                "vector_latency",
                {
                    "version_id": version_id,
                    "elapsed_ms": vec_elapsed_ms,
                    "window_size": VECTOR_WINDOW_SIZE,
                    "top_k": VECTOR_TOPK,
                },
            )
        else:
            meta["vector_error"] = "embedding_failed"
    elif VECTOR_ENABLED:
        meta["vector_skipped"] = "fts_empty"
    meta["vector_candidates"] = len(vector_items)
    if VECTOR_ENABLED and not vector_items:
        _log_event(
            "vector_zero",
            {"version_id": version_id, "window_size": VECTOR_WINDOW_SIZE},
        )
    items = _merge_candidates(fts_items, vector_items)
    meta["total_candidates"] = len(items)
    score_terms = keywords or topic_terms or synonyms
    scored = []
    for idx, item in enumerate(items):
        item.setdefault("source", "fts")
        text_norm = normalize_text(item["text"])
        keyword_hits = sum(1 for kw in score_terms if kw in text_norm) if score_terms else 0
        item["keyword_hits"] = keyword_hits
        vector_distance = item.get("vector_distance")
        vector_rank = vector_distance if vector_distance is not None else 9999.0
        rank = item.get("rank") or 0.0
        trgm_sim = item.get("trgm_sim") or 0.0
        scored.append((keyword_hits, -rank, -trgm_sim, vector_rank, idx, item))
    if score_terms or vector_items:
        scored.sort(key=lambda x: (-x[0], x[1], x[2], x[3], x[4]))
        items = [item for *_rest, item in scored]

    pre_rerank_order = _candidate_order(items)
    meta["rerank_mode"] = RERANK_MODE.lower()
    meta["rerank_applied"] = False
    meta["rerank_order_before"] = pre_rerank_order
    if RERANK_MODE.lower() != "off" and items:
        items = _rerank_candidates(context_text, items)
        meta["rerank_applied"] = any("rerank_score" in item for item in items)
        post_rerank_order = _candidate_order(items)
        meta["rerank_order_after"] = post_rerank_order
        meta["rerank_delta"] = _rerank_delta(pre_rerank_order, post_rerank_order)
    else:
        meta["rerank_order_after"] = pre_rerank_order
        meta["rerank_delta"] = []

    citations = []
    seen = set()
    for item in items:
        key = (item["book_id"], item["chapter"], item["verse"])
        if key in seen:
            continue
        seen.add(key)
        if not _passes_min_relevance(item, score_terms):
            continue
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
    meta["candidates"] = [
        {
            "book_id": item["book_id"],
            "chapter": item["chapter"],
            "verse": item["verse"],
            "rank": item.get("rank"),
            "trgm_sim": item.get("trgm_sim"),
            "vector_distance": item.get("vector_distance"),
            "keyword_hits": item.get("keyword_hits", 0),
            "rerank_score": item.get("rerank_score"),
            "source": item.get("source", "fts"),
        }
        for item in items[:10]
    ]
    if not citations:
        if meta["total_candidates"] == 0:
            meta["failure_reason"] = "no_results"
        else:
            meta["failure_reason"] = "below_threshold"
        return [], meta
    return citations, meta


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
