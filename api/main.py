import os
import time
import secrets
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import requests
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
    UserSettingsResponse,
    UserSettingsUpdateRequest,
    OAuthStartRequest,
    OAuthStartResponse,
    OAuthExchangeRequest,
    TokenResponse,
    RefreshRequest,
)
from api.auth import (
    create_session,
    create_user,
    create_user_oauth,
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
    update_last_login,
    validate_email,
    verify_captcha_token,
    verify_password,
)
from api.jwt_utils import (
    create_access_token,
    create_refresh_token,
    verify_access_token,
    verify_refresh_token,
)
from api.oauth_accounts import get_oauth_account, upsert_oauth_account
from api.oauth_google import build_google_auth_url, exchange_code_for_tokens, fetch_google_userinfo
from api.oauth_state import consume_oauth_state, store_oauth_state
from api.refresh_tokens import (
    get_refresh_token,
    is_refresh_token_active,
    revoke_refresh_token,
    store_refresh_token,
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
    openai_llm_enabled,
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
from api.chat_meta import (
    ANON_DAILY_TURN_LIMIT,
    ANON_CHAT_TURN_LIMIT,
    build_anonymous_meta_ttl,
    enforce_anonymous_daily_limit,
    get_anonymous_daily_usage,
    enforce_turn_and_increment,
    get_conversation_meta,
    init_conversation_meta,
)
from api.ref_parser import extract_reference, parse_reference
from api.search import search_verses
from api.user_settings import ensure_user_settings, get_user_settings, update_user_settings

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


def _get_user_from_jwt(token: str, conn) -> dict | None:
    payload = verify_access_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    user = get_user_by_id(conn, user_id)
    if not user:
        return None
    return user


def _remaining_turns(turn_limit: int | None, turn_count: int | None) -> int | None:
    if not turn_limit:
        return None
    return max(int(turn_limit) - int(turn_count or 0), 0)


def _meta_payload(meta: dict | None, turn_info: dict | None = None) -> dict:
    if not meta:
        return {
            "store_messages": None,
            "expires_at": None,
            "turn_limit": None,
            "turn_count": None,
            "remaining_turns": None,
            "daily_turn_limit": None,
            "daily_turn_count": None,
            "daily_remaining": None,
        }
    turn_limit = meta.get("turn_limit") or 0
    turn_count = meta.get("turn_count") or 0
    if turn_info and turn_info.get("status") == "ok":
        turn_limit = turn_info.get("turn_limit") or turn_limit
        turn_count = turn_info.get("turn_count") or turn_count
    return {
        "store_messages": meta.get("store_messages"),
        "expires_at": meta.get("expires_at"),
        "turn_limit": int(turn_limit) if turn_limit is not None else None,
        "turn_count": int(turn_count) if turn_count is not None else None,
        "remaining_turns": _remaining_turns(turn_limit, turn_count),
        "daily_turn_limit": None,
        "daily_turn_count": None,
        "daily_remaining": None,
    }


def _daily_payload(daily_info: dict | None) -> dict:
    if not daily_info:
        return {
            "daily_turn_limit": None,
            "daily_turn_count": None,
            "daily_remaining": None,
        }
    limit = int(daily_info.get("limit") or 0)
    count = int(daily_info.get("count") or 0)
    remaining = daily_info.get("remaining")
    if remaining is None and limit:
        remaining = max(limit - count, 0)
    return {
        "daily_turn_limit": limit or None,
        "daily_turn_count": count or 0,
        "daily_remaining": remaining if remaining is not None else None,
    }


def require_user(request: Request, conn=Depends(get_conn)) -> dict:
    token = _get_bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="auth required")
    user = _get_user_from_jwt(token, conn)
    if user:
        return user
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


def get_optional_user(request: Request, conn=Depends(get_conn)) -> dict | None:
    token = _get_bearer_token(request)
    if not token:
        return None
    user = _get_user_from_jwt(token, conn)
    if user:
        return user
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


@app.post("/v1/auth/register", response_model=TokenResponse)
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
    ensure_user_settings(conn, user["user_id"])
    update_last_login(conn, user["user_id"])
    access_token, access_exp = create_access_token(user["user_id"], email)
    refresh_token, refresh_id, refresh_exp = create_refresh_token(user["user_id"], email)
    store_refresh_token(conn, user["user_id"], refresh_id, refresh_exp, payload.device_id)
    conn.commit()
    return {
        "user_id": user["user_id"],
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": access_exp - int(datetime.now(timezone.utc).timestamp()),
        "token_type": "Bearer",
        "email": email,
    }


@app.post("/v1/auth/login", response_model=TokenResponse)
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

    update_last_login(conn, user["user_id"])
    access_token, access_exp = create_access_token(user["user_id"], user["email"])
    refresh_token, refresh_id, refresh_exp = create_refresh_token(user["user_id"], user["email"])
    store_refresh_token(conn, user["user_id"], refresh_id, refresh_exp, payload.device_id)
    conn.commit()
    return {
        "user_id": user["user_id"],
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": access_exp - int(datetime.now(timezone.utc).timestamp()),
        "token_type": "Bearer",
        "email": user.get("email"),
    }


@app.post("/v1/auth/oauth/google/start", response_model=OAuthStartResponse)
def oauth_google_start(payload: OAuthStartRequest):
    if not os.getenv("GOOGLE_CLIENT_ID"):
        raise HTTPException(status_code=503, detail="google oauth not configured")
    if not payload.redirect_uri or not payload.code_challenge:
        raise HTTPException(status_code=400, detail="invalid oauth request")
    state = secrets.token_urlsafe(24)
    store_oauth_state(
        state,
        {
            "provider": "google",
            "redirect_uri": payload.redirect_uri,
            "code_challenge": payload.code_challenge,
            "code_challenge_method": payload.code_challenge_method or "S256",
            "device_id": payload.device_id or "",
        },
    )
    auth_url = build_google_auth_url(
        redirect_uri=payload.redirect_uri,
        state=state,
        code_challenge=payload.code_challenge,
        code_challenge_method=payload.code_challenge_method or "S256",
    )
    return {"provider": "google", "auth_url": auth_url, "state": state}


def _pkce_verify(code_verifier: str, code_challenge: str, method: str) -> bool:
    if method.upper() != "S256":
        return False
    import base64
    import hashlib

    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return encoded == code_challenge


@app.post("/v1/auth/oauth/google/exchange", response_model=TokenResponse)
def oauth_google_exchange(payload: OAuthExchangeRequest, conn=Depends(get_conn)):
    if not os.getenv("GOOGLE_CLIENT_ID"):
        raise HTTPException(status_code=503, detail="google oauth not configured")
    state = consume_oauth_state(payload.state)
    if not state or state.get("provider") != "google":
        raise HTTPException(status_code=400, detail="invalid oauth state")
    if not _pkce_verify(payload.code_verifier, state.get("code_challenge", ""), state.get("code_challenge_method", "S256")):
        raise HTTPException(status_code=400, detail="invalid code_verifier")
    redirect_uri = state.get("redirect_uri") or ""
    try:
        token_data = exchange_code_for_tokens(payload.code, redirect_uri, payload.code_verifier)
        access_token = token_data.get("access_token", "")
        if not access_token:
            raise HTTPException(status_code=502, detail="google oauth failed")
        userinfo = fetch_google_userinfo(access_token)
    except requests.RequestException:
        raise HTTPException(status_code=502, detail="google oauth failed")

    provider_user_id = userinfo.get("sub")
    email = userinfo.get("email")
    email_verified = bool(userinfo.get("email_verified"))
    if not provider_user_id or not email:
        raise HTTPException(status_code=400, detail="google profile missing")
    if not email_verified:
        raise HTTPException(status_code=403, detail="email not verified")

    account = get_oauth_account(conn, "google", provider_user_id)
    if account:
        user_id = account["user_id"]
    else:
        existing_user = get_user_by_email(conn, email)
        if existing_user:
            user_id = existing_user["user_id"]
        else:
            user = create_user_oauth(conn, email)
            ensure_user_settings(conn, user["user_id"])
            user_id = user["user_id"]

    upsert_oauth_account(
        conn,
        "google",
        provider_user_id,
        user_id,
        email,
        email_verified,
        userinfo.get("name"),
        userinfo.get("picture"),
    )
    access_token, access_exp = create_access_token(user_id, email)
    refresh_token, refresh_id, refresh_exp = create_refresh_token(user_id, email)
    store_refresh_token(conn, user_id, refresh_id, refresh_exp, payload.device_id or "")
    conn.commit()

    return {
        "user_id": user_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": access_exp - int(datetime.now(timezone.utc).timestamp()),
        "token_type": "Bearer",
        "email": email,
    }


@app.post("/v1/auth/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshRequest, conn=Depends(get_conn)):
    refresh_payload = verify_refresh_token(payload.refresh_token)
    if not refresh_payload:
        raise HTTPException(status_code=401, detail="invalid refresh token")
    refresh_id = refresh_payload.get("jti")
    if not refresh_id:
        raise HTTPException(status_code=401, detail="invalid refresh token")
    record = get_refresh_token(conn, refresh_id)
    if not is_refresh_token_active(record):
        raise HTTPException(status_code=401, detail="refresh token revoked")
    user_id = refresh_payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="invalid refresh token")
    user = get_user_by_id(conn, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="user not found")

    revoke_refresh_token(conn, refresh_id)
    access_token, access_exp = create_access_token(user_id, user.get("email"))
    new_refresh_token, new_refresh_id, new_refresh_exp = create_refresh_token(user_id, user.get("email"))
    store_refresh_token(conn, user_id, new_refresh_id, new_refresh_exp, record.get("device_id") if record else None)
    conn.commit()
    return {
        "user_id": user_id,
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "expires_in": access_exp - int(datetime.now(timezone.utc).timestamp()),
        "token_type": "Bearer",
        "email": user.get("email"),
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
    payload = verify_refresh_token(token)
    if payload and payload.get("jti"):
        revoke_refresh_token(conn, payload["jti"])
        conn.commit()
        return {"revoked": True}
    revoked = revoke_session(conn, token)
    conn.commit()
    return {"revoked": revoked}


@app.get("/v1/users/me/settings", response_model=UserSettingsResponse)
def get_user_settings_api(current_user=Depends(require_user), conn=Depends(get_conn)):
    settings = get_user_settings(conn, current_user["user_id"])
    updated_at = settings.get("updated_at")
    return {
        "store_messages": bool(settings.get("store_messages")),
        "openai_citation_enabled": bool(settings.get("openai_citation_enabled")),
        "openai_api_key_set": bool(settings.get("openai_api_key")),
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


@app.patch("/v1/users/me/settings", response_model=UserSettingsResponse)
def update_user_settings_api(
    payload: UserSettingsUpdateRequest,
    current_user=Depends(require_user),
    conn=Depends(get_conn),
):
    settings = update_user_settings(
        conn,
        current_user["user_id"],
        payload.store_messages,
        payload.openai_citation_enabled,
        payload.openai_api_key,
    )
    conn.commit()
    updated_at = settings.get("updated_at")
    return {
        "store_messages": bool(settings.get("store_messages")),
        "openai_citation_enabled": bool(settings.get("openai_citation_enabled")),
        "openai_api_key_set": bool(settings.get("openai_api_key")),
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


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
def create_conversation(payload: ChatCreateRequest, request: Request, conn=Depends(get_conn)):
    current_user = get_optional_user(request, conn)
    effective_version_id = select_version_id(payload.locale)
    if current_user:
        settings = get_user_settings(conn, current_user["user_id"])
        store_messages = bool(settings.get("store_messages"))
        mode = "authenticated"
        expires_at = None
        turn_limit = 0
        turn_count = 0
        user_id = current_user["user_id"]
        daily_info = None
    else:
        store_messages = False
        mode = "anonymous"
        expires_at, _ttl_sec = build_anonymous_meta_ttl()
        turn_limit = ANON_CHAT_TURN_LIMIT
        turn_count = 0
        user_id = None
        device_id = (payload.device_id or "").strip()
        if device_id in {"web", "mobile"}:
            device_id = ""
        client_ip = _get_client_ip(request)
        identifier = device_id or client_ip
        scope = "device" if device_id else "ip"
        daily_info = get_anonymous_daily_usage(identifier, ANON_DAILY_TURN_LIMIT, scope=scope)

    record = store.create(
        payload.device_id,
        payload.locale,
        effective_version_id,
        store_messages=store_messages,
        conn=conn,
        mode=mode,
        expires_at=expires_at.isoformat() if expires_at else None,
        turn_limit=turn_limit,
        turn_count=turn_count,
        user_id=user_id,
    )
    try:
        meta = init_conversation_meta(
            record["conversation_id"],
            mode,
            store_messages,
            expires_at,
            turn_limit,
            turn_count,
            user_id=user_id,
            locale=payload.locale,
            version_id=effective_version_id,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="chat store unavailable")

    log_chat_event(
        "chat_created",
        {
            "conversation_id": record["conversation_id"],
            "version_id": record["version_id"],
            "store_messages": store_messages,
            "mode": mode,
        },
    )
    meta_payload = _meta_payload(meta)
    meta_payload.update(_daily_payload(daily_info))
    return {
        "conversation_id": record["conversation_id"],
        "created_at": record["created_at"],
        "store_messages": store_messages,
        "mode": mode,
        "expires_at": meta_payload["expires_at"],
        "turn_limit": meta_payload["turn_limit"],
        "turn_count": meta_payload["turn_count"],
        "remaining_turns": meta_payload["remaining_turns"],
        "daily_turn_limit": meta_payload["daily_turn_limit"],
        "daily_turn_count": meta_payload["daily_turn_count"],
        "daily_remaining": meta_payload["daily_remaining"],
    }


@app.get("/v1/chat/conversations/{conversation_id}", response_model=ChatConversationResponse)
def get_conversation(conversation_id: str, request: Request, conn=Depends(get_conn)):
    record = store.get(conversation_id, conn=conn)
    if not record:
        raise HTTPException(status_code=404, detail="conversation not found")
    meta = get_conversation_meta(conversation_id)
    daily_info = None
    if meta and meta.get("mode") == "anonymous":
        device_id = (record.get("device_id") or "").strip()
        if device_id in {"web", "mobile"}:
            device_id = ""
        client_ip = _get_client_ip(request)
        identifier = device_id or client_ip
        scope = "device" if device_id else "ip"
        daily_info = get_anonymous_daily_usage(identifier, ANON_DAILY_TURN_LIMIT, scope=scope)
    meta_payload = _meta_payload(meta)
    meta_payload.update(_daily_payload(daily_info))
    return {
        "conversation_id": record["conversation_id"],
        "created_at": record["created_at"],
        "version_id": record["version_id"],
        "store_messages": (
            meta_payload["store_messages"]
            if meta_payload["store_messages"] is not None
            else record.get("store_messages", False)
        ),
        "summary": record.get("summary", ""),
        "messages": record.get("messages", []),
        "mode": meta.get("mode") if meta else record.get("mode"),
        "expires_at": meta_payload["expires_at"],
        "turn_limit": meta_payload["turn_limit"],
        "turn_count": meta_payload["turn_count"],
        "remaining_turns": meta_payload["remaining_turns"],
        "daily_turn_limit": meta_payload["daily_turn_limit"],
        "daily_turn_count": meta_payload["daily_turn_count"],
        "daily_remaining": meta_payload["daily_remaining"],
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
def post_message(
    conversation_id: str,
    payload: ChatMessageRequest,
    request: Request = None,
    conn=Depends(get_conn),
):
    record = store.get(conversation_id, conn=conn)
    if not record:
        raise HTTPException(status_code=404, detail="conversation not found")
    meta = get_conversation_meta(conversation_id)
    if not meta:
        fallback_mode = record.get("mode") or (
            "authenticated" if record.get("store_messages") else "anonymous"
        )
        if fallback_mode == "anonymous":
            expires_at, _ttl_sec = build_anonymous_meta_ttl()
            turn_limit = ANON_CHAT_TURN_LIMIT
        else:
            expires_at = None
            turn_limit = 0
        try:
            meta = init_conversation_meta(
                conversation_id,
                fallback_mode,
                bool(record.get("store_messages")),
                expires_at,
                turn_limit,
                turn_count=int(record.get("turn_count") or 0),
                user_id=record.get("user_id"),
                locale=record.get("locale"),
                version_id=record.get("version_id"),
            )
        except Exception:
            raise HTTPException(status_code=503, detail="chat store unavailable")

    if meta.get("mode") == "anonymous":
        expires_at_text = meta.get("expires_at")
        if expires_at_text:
            try:
                expires_at = datetime.fromisoformat(expires_at_text)
                now = datetime.now(timezone.utc)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at <= now:
                    raise HTTPException(status_code=410, detail="session expired")
            except ValueError:
                pass
        device_id = (record.get("device_id") or "").strip()
        if device_id in {"web", "mobile"}:
            device_id = ""
        client_ip = _get_client_ip(request) if request else ""
        identifier = device_id or client_ip
        scope = "device" if device_id else "ip"
        daily_status = enforce_anonymous_daily_limit(
            identifier, ANON_DAILY_TURN_LIMIT, scope=scope
        )
        if daily_status.get("status") == "limit":
            raise HTTPException(status_code=429, detail="daily trial limit reached")
        daily_info = daily_status
    else:
        daily_info = None
    try:
        turn_info = enforce_turn_and_increment(conversation_id)
    except Exception:
        raise HTTPException(status_code=503, detail="chat store unavailable")
    if turn_info.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="conversation not found")
    if turn_info.get("status") == "expired":
        raise HTTPException(status_code=410, detail="session expired")
    if turn_info.get("status") == "limit":
        raise HTTPException(status_code=429, detail="trial limit reached")
    meta_payload = _meta_payload(meta, turn_info)
    meta_payload.update(_daily_payload(daily_info))
    record["store_messages"] = bool(meta_payload.get("store_messages"))
    record["mode"] = meta.get("mode")
    record["expires_at"] = meta_payload.get("expires_at")
    record["turn_limit"] = meta_payload.get("turn_limit")
    record["turn_count"] = meta_payload.get("turn_count")

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
                **meta_payload,
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
                **meta_payload,
            },
        }

    openai_api_key = None
    use_openai_llm = False
    if record.get("user_id"):
        user_settings = get_user_settings(conn, record["user_id"], include_secrets=True)
        openai_api_key = user_settings.get("openai_api_key")
        if user_settings.get("openai_citation_enabled") and openai_llm_enabled(openai_api_key):
            use_openai_llm = True

    if len(record["messages"]) >= SUMMARY_TRIGGER_TURNS:
        summary = summarize_messages(
            record["messages"],
            record.get("summary", ""),
            use_openai=use_openai_llm,
            openai_api_key=openai_api_key,
        )
        store.set_summary(conversation_id, summary, conn=conn)
    else:
        summary = record.get("summary", "")

    recent_messages = record["messages"][-RECENT_TURNS:]
    gating = gate_need_verse(
        sanitized_message,
        summary,
        recent_messages,
        use_openai=use_openai_llm,
        openai_api_key=openai_api_key,
    )
    assistant_message, llm_ok = build_assistant_message(
        sanitized_message,
        gating,
        summary,
        recent_messages,
        use_openai=use_openai_llm,
        openai_api_key=openai_api_key,
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
            use_openai=use_openai_llm,
            openai_api_key=openai_api_key,
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
            **meta_payload,
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "9000"))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=True)
