import os
import time
from datetime import datetime, timezone
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import API_TITLE, API_VERSION, DB
from api.models import (
    AuthLoginRequest,
    AuthLogoutResponse,
    AuthMeResponse,
    AuthRegisterRequest,
    AuthResponse,
    BooksResponse,
    ChapterResponse,
    ChatConversationResponse,
    ChatCreateRequest,
    ChatCreateResponse,
    ChatDeleteResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    BookmarkRequest,
    BookmarkItem,
    BookmarkListResponse,
    BookmarkCreateResponse,
    BookmarkDeleteResponse,
    MemoRequest,
    MemoItem,
    MemoListResponse,
    MemoUpsertResponse,
    MemoDeleteResponse,
    RefResponse,
    SearchResponse,
)
from api.auth import (
    create_session,
    create_user,
    clear_login_attempt,
    get_session,
    get_login_attempt,
    get_user_by_email,
    get_user_by_id,
    hash_password,
    is_login_blocked,
    login_retry_after,
    normalize_email,
    needs_password_upgrade,
    record_login_failure,
    requires_captcha,
    revoke_session,
    touch_session,
    update_password_hash,
    validate_email,
    verify_captcha_token,
    verify_password,
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
    select_version_id,
    select_citation_version_id,
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


def _get_bearer_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        return None
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _get_client_ip(request: Request) -> str:
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def require_user(request: Request, conn=Depends(get_conn)) -> dict:
    token = _get_bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="auth required")
    session = get_session(conn, token)
    if not session:
        raise HTTPException(status_code=401, detail="invalid session")
    expires_at = session.get("expires_at")
    if expires_at and expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="session expired")
    user = get_user_by_id(conn, session["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="user not found")
    touch_session(conn, token)
    conn.commit()
    return user


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


@app.post("/v1/auth/register", response_model=AuthResponse)
def register(payload: AuthRegisterRequest, conn=Depends(get_conn)):
    email = normalize_email(payload.email)
    if not validate_email(email):
        raise HTTPException(status_code=400, detail="invalid email")
    password = payload.password or ""
    if len(password) < 12:
        raise HTTPException(status_code=400, detail="password too short")
    if len(password) > 128:
        raise HTTPException(status_code=400, detail="password too long")
    existing = get_user_by_email(conn, email)
    if existing:
        raise HTTPException(status_code=409, detail="email already registered")
    user = create_user(conn, email, payload.password)
    session = create_session(conn, user["user_id"], payload.device_id)
    conn.commit()
    return {
        "user_id": user["user_id"],
        "session_token": session["session_token"],
        "expires_at": session["expires_at"].isoformat(),
    }


@app.post("/v1/auth/login", response_model=AuthResponse)
def login(payload: AuthLoginRequest, request: Request, conn=Depends(get_conn)):
    email = normalize_email(payload.email)
    ip_address = _get_client_ip(request)
    now = datetime.now(timezone.utc)

    account_attempt = get_login_attempt(conn, "account", email) if email else None
    ip_attempt = get_login_attempt(conn, "ip", ip_address) if ip_address else None
    if is_login_blocked(account_attempt, now) or is_login_blocked(ip_attempt, now):
        retry_after = max(
            login_retry_after(account_attempt, now),
            login_retry_after(ip_attempt, now),
        )
        raise HTTPException(
            status_code=429,
            detail=f"login temporarily blocked, retry after {retry_after}s",
        )

    if requires_captcha(account_attempt) or requires_captcha(ip_attempt):
        if not verify_captcha_token(payload.captcha_token):
            raise HTTPException(status_code=403, detail="captcha required")

    user = get_user_by_email(conn, email)
    if not user or not verify_password(payload.password or "", user["password_hash"]):
        if email:
            record_login_failure(conn, "account", email, now)
        if ip_address:
            record_login_failure(conn, "ip", ip_address, now)
        conn.commit()
        raise HTTPException(status_code=401, detail="invalid credentials")

    if needs_password_upgrade(user["password_hash"]):
        update_password_hash(conn, user["user_id"], hash_password(payload.password or ""))

    if email:
        clear_login_attempt(conn, "account", email)
    if ip_address:
        clear_login_attempt(conn, "ip", ip_address)

    session = create_session(conn, user["user_id"], payload.device_id)
    conn.commit()
    return {
        "user_id": user["user_id"],
        "session_token": session["session_token"],
        "expires_at": session["expires_at"].isoformat(),
    }


@app.get("/v1/auth/me", response_model=AuthMeResponse)
def me(current_user=Depends(require_user)):
    return {
        "user_id": current_user["user_id"],
        "email": current_user["email"],
        "created_at": current_user["created_at"].isoformat(),
        "last_login": current_user["last_login"].isoformat()
        if current_user.get("last_login")
        else None,
    }


@app.post("/v1/auth/logout", response_model=AuthLogoutResponse)
def logout(request: Request, conn=Depends(get_conn)):
    token = _get_bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="auth required")
    revoked = revoke_session(conn, token)
    conn.commit()
    return {"revoked": revoked}


@app.get("/v1/bible/bookmarks", response_model=BookmarkListResponse)
def list_bookmarks(
    current_user=Depends(require_user),
    version_id: str = Query("krv"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn=Depends(get_conn),
):
    user_id = current_user["user_id"]
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                m.user_id,
                m.version_id,
                m.book_id,
                b.ko_name AS book_name,
                m.chapter,
                m.verse,
                m.created_at
            FROM bible_bookmark m
            JOIN bible_book b
              ON b.version_id = m.version_id AND b.book_id = m.book_id
            WHERE m.user_id = %s AND m.version_id = %s
            ORDER BY m.created_at DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, version_id, limit, offset),
        )
        rows = cur.fetchall()
    items = [
        {
            "version_id": row["version_id"],
            "book_id": row["book_id"],
            "book_name": row["book_name"],
            "chapter": row["chapter"],
            "verse": row["verse"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]
    return {"items": items}


@app.post("/v1/bible/bookmarks", response_model=BookmarkCreateResponse)
def create_bookmark(payload: BookmarkRequest, current_user=Depends(require_user), conn=Depends(get_conn)):
    user_id = current_user["user_id"]
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bible_bookmark (device_id, user_id, version_id, book_id, chapter, verse)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (device_id, version_id, book_id, chapter, verse)
            DO NOTHING
            """,
            (
                user_id,
                user_id,
                payload.version_id,
                payload.book_id,
                payload.chapter,
                payload.verse,
            ),
        )
        created = cur.rowcount > 0
    conn.commit()
    return {"created": created}


@app.delete("/v1/bible/bookmarks", response_model=BookmarkDeleteResponse)
def delete_bookmark(
    current_user=Depends(require_user),
    version_id: str = Query("krv"),
    book_id: int = Query(...),
    chapter: int = Query(...),
    verse: int = Query(...),
    conn=Depends(get_conn),
):
    user_id = current_user["user_id"]
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM bible_bookmark
            WHERE user_id = %s AND version_id = %s
              AND book_id = %s AND chapter = %s AND verse = %s
            """,
            (user_id, version_id, book_id, chapter, verse),
        )
        deleted = cur.rowcount > 0
    conn.commit()
    return {"deleted": deleted}


@app.get("/v1/bible/memos", response_model=MemoListResponse)
def list_memos(
    current_user=Depends(require_user),
    version_id: str = Query("krv"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn=Depends(get_conn),
):
    user_id = current_user["user_id"]
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                m.user_id,
                m.version_id,
                m.book_id,
                b.ko_name AS book_name,
                m.chapter,
                m.verse,
                m.memo_text,
                m.created_at,
                m.updated_at
            FROM bible_memo m
            JOIN bible_book b
              ON b.version_id = m.version_id AND b.book_id = m.book_id
            WHERE m.user_id = %s AND m.version_id = %s
            ORDER BY m.updated_at DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, version_id, limit, offset),
        )
        rows = cur.fetchall()
    items = [
        {
            "version_id": row["version_id"],
            "book_id": row["book_id"],
            "book_name": row["book_name"],
            "chapter": row["chapter"],
            "verse": row["verse"],
            "memo_text": row["memo_text"],
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
        }
        for row in rows
    ]
    return {"items": items}


@app.post("/v1/bible/memos", response_model=MemoUpsertResponse)
def upsert_memo(payload: MemoRequest, current_user=Depends(require_user), conn=Depends(get_conn)):
    user_id = current_user["user_id"]
    memo_text = (payload.memo_text or "").strip()
    if not memo_text:
        raise HTTPException(status_code=400, detail="memo_text required")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bible_memo
              (device_id, user_id, version_id, book_id, chapter, verse, memo_text)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (device_id, version_id, book_id, chapter, verse)
            DO UPDATE SET memo_text = EXCLUDED.memo_text, updated_at = now()
            """,
            (
                user_id,
                user_id,
                payload.version_id,
                payload.book_id,
                payload.chapter,
                payload.verse,
                memo_text,
            ),
        )
    conn.commit()
    return {"saved": True}


@app.delete("/v1/bible/memos", response_model=MemoDeleteResponse)
def delete_memo(
    current_user=Depends(require_user),
    version_id: str = Query("krv"),
    book_id: int = Query(...),
    chapter: int = Query(...),
    verse: int = Query(...),
    conn=Depends(get_conn),
):
    user_id = current_user["user_id"]
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM bible_memo
            WHERE user_id = %s AND version_id = %s
              AND book_id = %s AND chapter = %s AND verse = %s
            """,
            (user_id, version_id, book_id, chapter, verse),
        )
        deleted = cur.rowcount > 0
    conn.commit()
    return {"deleted": deleted}


@app.post("/v1/chat/conversations", response_model=ChatCreateResponse)
def create_conversation(payload: ChatCreateRequest, conn=Depends(get_conn)):
    effective_version_id = select_version_id(payload.locale)
    record = store.create(
        payload.device_id,
        payload.locale,
        effective_version_id,
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
    citation_version_id = select_citation_version_id(record.get("locale"), sanitized_message)
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
                citation_version_id,
                book_name,
                ch,
                vs_start,
            )
            citations.append(
                {
                    "version_id": citation_version_id,
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
                citation_version_id,
                book_name,
                ch,
                vs_start,
                vs_end,
            )
            for item in verse_payload["verses"]:
                citations.append(
                    {
                        "version_id": citation_version_id,
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
        turn_index = len(record["messages"])
        log_chat_event(
            "citation_attempt",
            {
                "conversation_id": conversation_id,
                "turn_index": turn_index,
                "need_verse": True,
                "source": "direct_reference",
                "trigger_reason": ["direct_reference"],
                "exclude_reason": [],
                "topics": [],
                "user_goal": "",
            },
        )
        if citations:
            log_chat_event(
                "citation_selected",
                {
                    "conversation_id": conversation_id,
                    "turn_index": turn_index,
                    "selected": [
                        {
                            "book_id": c["book_id"],
                            "chapter": c["chapter"],
                            "verse_start": c["verse_start"],
                            "verse_end": c["verse_end"],
                        }
                        for c in citations
                    ],
                },
            )
        else:
            log_chat_event(
                "citation_failure",
                {
                    "conversation_id": conversation_id,
                    "turn_index": turn_index,
                    "reason": "direct_reference_not_found",
                },
            )
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
                    "trigger_reason": ["direct_reference"],
                    "exclude_reason": [],
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
                    "trigger_reason": [],
                    "exclude_reason": [],
                },
            },
        }

    if len(record["messages"]) >= SUMMARY_TRIGGER_TURNS:
        summary = summarize_messages(record["messages"], record.get("summary", ""))
        store.set_summary(conversation_id, summary, conn=conn)
    else:
        summary = record.get("summary", "")

    recent_messages = record["messages"][-RECENT_TURNS:]
    gating = gate_need_verse(sanitized_message, summary, recent_messages)
    assistant_message, llm_ok = build_assistant_message(
        sanitized_message, gating, summary, recent_messages
    )
    gating["llm_ok"] = llm_ok
    if not llm_ok:
        gating["need_verse"] = False
        gating["source"] = "degraded"
    citations = []
    if gating.get("need_verse"):
        turn_index = len(record["messages"])
        log_chat_event(
            "citation_attempt",
            {
                "conversation_id": conversation_id,
                "turn_index": turn_index,
                "need_verse": gating.get("need_verse", False),
                "source": gating.get("source", ""),
                "trigger_reason": gating.get("trigger_reason", []),
                "exclude_reason": gating.get("exclude_reason", []),
                "topics": gating.get("topics", []),
                "user_goal": gating.get("user_goal", ""),
            },
        )
        citations, retrieval_meta = retrieve_citations(
            conn,
            citation_version_id,
            sanitized_message,
            summary=summary,
            recent_messages=recent_messages,
        )
        log_chat_event(
            "retrieval_candidates",
            {
                "conversation_id": conversation_id,
                "turn_index": turn_index,
                **retrieval_meta,
            },
        )
        assistant_message = append_citations_to_response(assistant_message, citations)
    citations = _verify_citations(conn, citations)
    if gating.get("need_verse"):
        if citations:
            log_chat_event(
                "citation_selected",
                {
                    "conversation_id": conversation_id,
                    "turn_index": turn_index,
                    "selected": [
                        {
                            "book_id": c["book_id"],
                            "chapter": c["chapter"],
                            "verse_start": c["verse_start"],
                            "verse_end": c["verse_end"],
                        }
                        for c in citations
                    ],
                },
            )
        else:
            log_chat_event(
                "citation_failure",
                {
                    "conversation_id": conversation_id,
                    "turn_index": turn_index,
                    "reason": retrieval_meta.get("failure_reason") or "verification_failed",
                },
            )
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


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "9000"))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=True)
