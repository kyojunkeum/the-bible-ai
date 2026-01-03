import os
import time
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import API_TITLE, API_VERSION, DB
from api.models import (
    BooksResponse,
    ChapterResponse,
    ChatConversationResponse,
    ChatCreateRequest,
    ChatCreateResponse,
    ChatDeleteResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    RefResponse,
    SearchResponse,
)
from api.chat import (
    append_citations_to_response,
    build_assistant_message,
    CRISIS_RESPONSE,
    enforce_exact_citations,
    gate_need_verse,
    log_chat_event,
    log_search_event,
    log_verse_cited,
    retrieve_citations,
    store,
    summarize_messages,
    _mask_pii,
    _risk_flags,
    SUMMARY_TRIGGER_TURNS,
    RECENT_TURNS,
)
from api.ref_parser import extract_reference, parse_reference
from api.search import search_verses

app = FastAPI(title=API_TITLE, version=API_VERSION)

CORS_ALLOW_ALL = os.getenv("CORS_ALLOW_ALL", "1") == "1"
if CORS_ALLOW_ALL:
    allow_origins = ["*"]
else:
    raw_origins = os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    allow_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
def handle_http_exception(_request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail)}},
    )


@app.exception_handler(RequestValidationError)
def handle_validation_exception(_request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "invalid request",
                "details": exc.errors(),
            }
        },
    )


def get_conn():
    conn = psycopg2.connect(**DB)
    try:
        yield conn
    finally:
        conn.close()


def _fetch_book_and_verse(conn, version_id: str, book_name: str, chapter: int, verse: int) -> dict:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if book_name.isdigit():
            cur.execute(
                """
                SELECT book_id, ko_name
                FROM bible_book
                WHERE version_id = %s AND book_id = %s
                """,
                (version_id, int(book_name)),
            )
        else:
            cur.execute(
                """
                SELECT book_id, ko_name
                FROM bible_book
                WHERE version_id = %s
                  AND (ko_name = %s OR abbr = %s OR upper(osis_code) = upper(%s))
                """,
                (version_id, book_name, book_name, book_name),
            )

        book_row = cur.fetchone()
        if not book_row:
            raise HTTPException(status_code=404, detail="book not found")

        cur.execute(
            """
            SELECT text
            FROM bible_verse
            WHERE version_id = %s AND book_id = %s AND chapter = %s AND verse = %s
            """,
            (version_id, book_row["book_id"], chapter, verse),
        )
        verse_row = cur.fetchone()
        if not verse_row:
            raise HTTPException(status_code=404, detail="verse not found")

    return {
        "book_id": book_row["book_id"],
        "book_name": book_row["ko_name"],
        "chapter": chapter,
        "verse": verse,
        "text": verse_row["text"],
    }


def _fetch_book_and_range(
    conn, version_id: str, book_name: str, chapter: int, verse_start: int, verse_end: int
) -> dict:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if book_name.isdigit():
            cur.execute(
                """
                SELECT book_id, ko_name
                FROM bible_book
                WHERE version_id = %s AND book_id = %s
                """,
                (version_id, int(book_name)),
            )
        else:
            cur.execute(
                """
                SELECT book_id, ko_name
                FROM bible_book
                WHERE version_id = %s
                  AND (ko_name = %s OR abbr = %s OR upper(osis_code) = upper(%s))
                """,
                (version_id, book_name, book_name, book_name),
            )

        book_row = cur.fetchone()
        if not book_row:
            raise HTTPException(status_code=404, detail="book not found")

        cur.execute(
            """
            SELECT verse, text
            FROM bible_verse
            WHERE version_id = %s AND book_id = %s AND chapter = %s
              AND verse BETWEEN %s AND %s
            ORDER BY verse
            """,
            (version_id, book_row["book_id"], chapter, verse_start, verse_end),
        )
        verse_rows = cur.fetchall()
        if not verse_rows:
            raise HTTPException(status_code=404, detail="verse not found")

    return {
        "book_id": book_row["book_id"],
        "book_name": book_row["ko_name"],
        "chapter": chapter,
        "verses": [{"verse": row["verse"], "text": row["text"]} for row in verse_rows],
    }


def _verify_citations(conn, citations: list[dict]) -> list[dict]:
    if not citations:
        return citations

    verified = []
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        for c in citations:
            cur.execute(
                """
                SELECT text
                FROM bible_verse
                WHERE version_id = %s AND book_id = %s AND chapter = %s AND verse = %s
                """,
                (c["version_id"], c["book_id"], c["chapter"], c["verse_start"]),
            )
            row = cur.fetchone()
            if not row:
                continue
            if row["text"] != c["text"]:
                continue
            verified.append(c)
    return verified


@app.get("/v1/bible/{version_id}/books", response_model=BooksResponse)
def list_books(version_id: str, conn=Depends(get_conn)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT book_id, osis_code, ko_name, abbr, chapter_count, testament
            FROM bible_book
            WHERE version_id = %s
            ORDER BY book_id
            """,
            (version_id,),
        )
        rows = cur.fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="version not found")

    return {"items": rows}


@app.get(
    "/v1/bible/{version_id}/books/{book_id}/chapters/{chapter}",
    response_model=ChapterResponse,
)
def get_chapter(version_id: str, book_id: int, chapter: int, conn=Depends(get_conn)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT content_hash
            FROM bible_chapter_hash
            WHERE version_id = %s AND book_id = %s AND chapter = %s
            """,
            (version_id, book_id, chapter),
        )
        hash_row = cur.fetchone()
        if not hash_row:
            raise HTTPException(status_code=404, detail="chapter not found")

        cur.execute(
            """
            SELECT verse, text
            FROM bible_verse
            WHERE version_id = %s AND book_id = %s AND chapter = %s
            ORDER BY verse
            """,
            (version_id, book_id, chapter),
        )
        verses = cur.fetchall()

    return {"content_hash": hash_row["content_hash"], "verses": verses}


@app.get("/v1/bible/{version_id}/ref", response_model=RefResponse)
def get_ref(
    version_id: str,
    book: str = Query(...),
    chapter: Optional[int] = None,
    verse: Optional[int] = None,
    conn=Depends(get_conn),
):
    try:
        book_name, ch, vs = parse_reference(book, chapter, verse)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid reference")
    return _fetch_book_and_verse(conn, version_id, book_name, ch, vs)


@app.get("/v1/bible/{version_id}/search", response_model=SearchResponse)
def search(
    version_id: str,
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn=Depends(get_conn),
):
    start = time.perf_counter()
    results = search_verses(conn, version_id, q, limit, offset)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    log_search_event(
        "search_latency",
        {"version_id": version_id, "elapsed_ms": elapsed_ms, "q": q, "total": results.get("total", 0)},
    )
    slow_ms = int(os.getenv("SEARCH_SLOW_MS", "500"))
    if elapsed_ms > slow_ms:
        log_search_event(
            "search_slow",
            {"version_id": version_id, "elapsed_ms": elapsed_ms, "q": q},
        )
    if results.get("total", 0) == 0:
        log_search_event("search_zero", {"version_id": version_id, "q": q})
    return results


@app.post("/v1/chat/conversations", response_model=ChatCreateResponse)
def create_conversation(payload: ChatCreateRequest, conn=Depends(get_conn)):
    record = store.create(
        payload.device_id,
        payload.locale,
        payload.version_id,
        store_messages=payload.store_messages,
        conn=conn,
    )
    log_chat_event(
        "chat_created",
        {
            "conversation_id": record["conversation_id"],
            "version_id": record["version_id"],
            "store_messages": record["store_messages"],
        },
    )
    return {
        "conversation_id": record["conversation_id"],
        "created_at": record["created_at"],
        "store_messages": record["store_messages"],
    }


@app.get("/v1/chat/conversations/{conversation_id}", response_model=ChatConversationResponse)
def get_conversation(conversation_id: str, conn=Depends(get_conn)):
    record = store.get(conversation_id, conn=conn)
    if not record:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {
        "conversation_id": record["conversation_id"],
        "created_at": record["created_at"],
        "version_id": record["version_id"],
        "store_messages": record.get("store_messages", False),
        "summary": record.get("summary", ""),
        "messages": record.get("messages", []),
    }


@app.delete("/v1/chat/conversations/{conversation_id}", response_model=ChatDeleteResponse)
def delete_conversation(conversation_id: str, conn=Depends(get_conn)):
    deleted = store.delete(conversation_id, conn=conn)
    if not deleted:
        raise HTTPException(status_code=404, detail="conversation not found")
    log_chat_event("chat_deleted", {"conversation_id": conversation_id})
    return {"deleted": deleted}


@app.post(
    "/v1/chat/conversations/{conversation_id}/messages",
    response_model=ChatMessageResponse,
)
def post_message(conversation_id: str, payload: ChatMessageRequest, conn=Depends(get_conn)):
    record = store.get(conversation_id, conn=conn)
    if not record:
        raise HTTPException(status_code=404, detail="conversation not found")

    sanitized_message = _mask_pii(payload.user_message)
    store.add_message(conversation_id, "user", sanitized_message, conn=conn)
    log_chat_event(
        "chat_message",
        {
            "conversation_id": conversation_id,
            "role": "user",
            "store_messages": record.get("store_messages", False),
        },
    )

    direct_ref = extract_reference(sanitized_message)
    if direct_ref:
        book_name, ch, vs_start, vs_end = direct_ref
        citations = []
        if vs_end == vs_start:
            verse_payload = _fetch_book_and_verse(
                conn,
                record.get("version_id", "krv"),
                book_name,
                ch,
                vs_start,
            )
            citations.append(
                {
                    "version_id": record.get("version_id", "krv"),
                    "book_id": verse_payload["book_id"],
                    "book_name": verse_payload["book_name"],
                    "chapter": verse_payload["chapter"],
                    "verse_start": verse_payload["verse"],
                    "verse_end": verse_payload["verse"],
                    "text": verse_payload["text"],
                }
            )
        else:
            verse_payload = _fetch_book_and_range(
                conn,
                record.get("version_id", "krv"),
                book_name,
                ch,
                vs_start,
                vs_end,
            )
            for item in verse_payload["verses"]:
                citations.append(
                    {
                        "version_id": record.get("version_id", "krv"),
                        "book_id": verse_payload["book_id"],
                        "book_name": verse_payload["book_name"],
                        "chapter": verse_payload["chapter"],
                        "verse_start": item["verse"],
                        "verse_end": item["verse"],
                        "text": item["text"],
                    }
                )
        citations = _verify_citations(conn, citations)
        assistant_message = append_citations_to_response("", citations)
        assistant_message, citations = enforce_exact_citations(assistant_message, citations)
        store.add_message(conversation_id, "assistant", assistant_message, conn=conn)
        log_chat_event(
            "chat_response",
            {
                "conversation_id": conversation_id,
                "citations_count": len(citations),
                "direct_reference": True,
            },
        )
        log_verse_cited(conversation_id, citations)
        return {
            "assistant_message": assistant_message,
            "citations": citations,
            "memory": {
                "mode": "recent",
                "recent_turns": len(record["messages"][-RECENT_TURNS:]),
                "summary": record.get("summary", ""),
                "gating": {
                    "need_verse": True,
                    "topics": [],
                    "user_goal": "",
                    "risk_flags": [],
                    "llm_ok": False,
                    "source": "direct_reference",
                },
                "direct_reference": True,
            },
        }

    risk_flags = _risk_flags(sanitized_message)
    if risk_flags:
        assistant_message = CRISIS_RESPONSE
        store.add_message(conversation_id, "assistant", assistant_message, conn=conn)
        log_chat_event(
            "chat_crisis",
            {
                "conversation_id": conversation_id,
                "risk_flags": risk_flags,
                "store_messages": record.get("store_messages", False),
            },
        )
        return {
            "assistant_message": assistant_message,
            "citations": [],
            "memory": {
                "mode": "recent",
                "recent_turns": len(record["messages"][-RECENT_TURNS:]),
                "summary": record.get("summary", ""),
                "gating": {
                    "need_verse": False,
                    "topics": [],
                    "user_goal": "",
                    "risk_flags": risk_flags,
                    "llm_ok": False,
                    "source": "crisis",
                },
            },
        }

    assistant_turns = sum(
        1 for m in record.get("messages", []) if m.get("role") == "assistant"
    )
    force_citation = (assistant_turns + 1) % 5 == 0

    gating = gate_need_verse(sanitized_message)
    if force_citation:
        gating["need_verse"] = True
        gating["source"] = "periodic"

    if len(record["messages"]) >= SUMMARY_TRIGGER_TURNS:
        summary = summarize_messages(record["messages"], record.get("summary", ""))
        store.set_summary(conversation_id, summary, conn=conn)
    else:
        summary = record.get("summary", "")

    recent_messages = record["messages"][-RECENT_TURNS:]
    assistant_message, llm_ok = build_assistant_message(
        sanitized_message, gating, summary, recent_messages
    )
    gating["llm_ok"] = llm_ok
    if not llm_ok and not force_citation:
        gating["need_verse"] = False
        gating["source"] = "degraded"
    citations = []
    if gating.get("need_verse"):
        citations = retrieve_citations(conn, record.get("version_id", "krv"), sanitized_message)
        assistant_message = append_citations_to_response(assistant_message, citations)
    citations = _verify_citations(conn, citations)
    assistant_message, citations = enforce_exact_citations(assistant_message, citations)
    store.add_message(conversation_id, "assistant", assistant_message, conn=conn)
    log_chat_event(
        "chat_response",
        {
            "conversation_id": conversation_id,
            "citations_count": len(citations),
            "need_verse": gating.get("need_verse", False),
            "llm_ok": llm_ok,
            "store_messages": record.get("store_messages", False),
        },
    )
    log_verse_cited(conversation_id, citations)

    return {
        "assistant_message": assistant_message,
        "citations": citations,
        "memory": {
            "mode": "recent+summary" if summary else "recent",
            "recent_turns": len(recent_messages),
            "summary": summary,
            "gating": gating,
        },
    }


@app.get("/v1/chat/conversations/{conversation_id}", response_model=ChatConversationResponse)
def get_conversation(conversation_id: str, conn=Depends(get_conn)):
    record = store.get(conversation_id, conn=conn)
    if not record:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {
        "conversation_id": record["conversation_id"],
        "created_at": record["created_at"],
        "messages": record["messages"],
    }


@app.delete("/v1/chat/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, conn=Depends(get_conn)):
    deleted = store.delete(conversation_id, conn=conn)
    if not deleted:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "9000"))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=True)
