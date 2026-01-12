from typing import List, Optional
from pydantic import BaseModel


class BookItem(BaseModel):
    book_id: int
    osis_code: str
    ko_name: str
    abbr: str
    chapter_count: int
    testament: str


class BooksResponse(BaseModel):
    items: List[BookItem]


class VerseItem(BaseModel):
    verse: int
    text: str


class ChapterResponse(BaseModel):
    content_hash: str
    verses: List[VerseItem]


class RefResponse(BaseModel):
    book_id: int
    book_name: str
    chapter: int
    verse: int
    text: str


class SearchItem(BaseModel):
    book_id: int
    book_name: str
    chapter: int
    verse: int
    snippet: str
    text: str


class SearchResponse(BaseModel):
    total: int
    items: List[SearchItem]


class BookmarkRequest(BaseModel):
    version_id: str = "krv"
    book_id: int
    chapter: int
    verse: int


class BookmarkItem(BaseModel):
    version_id: str
    book_id: int
    book_name: str
    chapter: int
    verse: int
    created_at: str


class BookmarkListResponse(BaseModel):
    items: List[BookmarkItem]


class BookmarkCreateResponse(BaseModel):
    created: bool


class BookmarkDeleteResponse(BaseModel):
    deleted: bool


class MemoRequest(BaseModel):
    version_id: str = "krv"
    book_id: int
    chapter: int
    verse: int
    memo_text: str


class MemoItem(BaseModel):
    version_id: str
    book_id: int
    book_name: str
    chapter: int
    verse: int
    memo_text: str
    created_at: str
    updated_at: str


class MemoListResponse(BaseModel):
    items: List[MemoItem]


class MemoUpsertResponse(BaseModel):
    saved: bool


class MemoDeleteResponse(BaseModel):
    deleted: bool


class ChatCreateRequest(BaseModel):
    device_id: str | None = None
    locale: str | None = None
    version_id: str = "krv"
    store_messages: bool = False


class ChatCreateResponse(BaseModel):
    conversation_id: str
    created_at: str
    store_messages: bool = False
    mode: str | None = None
    expires_at: str | None = None
    turn_limit: int | None = None
    turn_count: int | None = None
    remaining_turns: int | None = None
    daily_turn_limit: int | None = None
    daily_turn_count: int | None = None
    daily_remaining: int | None = None


class ChatMessageRequest(BaseModel):
    user_message: str
    client_context: dict | None = None


class ChatCitation(BaseModel):
    version_id: str
    book_id: int
    book_name: str
    chapter: int
    verse_start: int
    verse_end: int
    text: str


class ChatGating(BaseModel):
    need_verse: bool
    topics: List[str] = []
    user_goal: str = ""
    risk_flags: List[str] = []
    llm_ok: bool = True
    source: str = "llm"
    trigger_reason: List[str] = []
    exclude_reason: List[str] = []


class ChatMemory(BaseModel):
    mode: str
    recent_turns: int
    summary: str = ""
    gating: Optional[ChatGating] = None
    direct_reference: Optional[bool] = None
    store_messages: Optional[bool] = None
    expires_at: Optional[str] = None
    turn_limit: Optional[int] = None
    turn_count: Optional[int] = None
    remaining_turns: Optional[int] = None
    daily_turn_limit: Optional[int] = None
    daily_turn_count: Optional[int] = None
    daily_remaining: Optional[int] = None


class ChatMessageResponse(BaseModel):
    assistant_message: str
    citations: List[ChatCitation] = []
    memory: ChatMemory


class ChatConversationResponse(BaseModel):
    conversation_id: str
    created_at: str
    version_id: str
    store_messages: bool
    summary: str = ""
    messages: List[dict]
    mode: str | None = None
    expires_at: str | None = None
    turn_limit: int | None = None
    turn_count: int | None = None
    remaining_turns: int | None = None
    daily_turn_limit: int | None = None
    daily_turn_count: int | None = None
    daily_remaining: int | None = None


class ChatDeleteResponse(BaseModel):
    deleted: bool


class AuthRegisterRequest(BaseModel):
    email: str
    password: str
    device_id: str | None = None


class AuthLoginRequest(BaseModel):
    email: str
    password: str
    captcha_token: str | None = None
    device_id: str | None = None


class AuthResponse(BaseModel):
    user_id: str
    session_token: str
    expires_at: str


class AuthLogoutResponse(BaseModel):
    revoked: bool


class AuthMeResponse(BaseModel):
    user_id: str
    email: str
    created_at: str
    last_login: str | None = None


class UserSettingsResponse(BaseModel):
    store_messages: bool
    openai_citation_enabled: bool = False
    openai_api_key_set: bool = False
    updated_at: str | None = None


class UserSettingsUpdateRequest(BaseModel):
    store_messages: Optional[bool] = None
    openai_citation_enabled: Optional[bool] = None
    openai_api_key: Optional[str] = None


class OAuthStartRequest(BaseModel):
    redirect_uri: str
    code_challenge: str
    code_challenge_method: str = "S256"
    device_id: str | None = None
    client_id: str | None = None


class OAuthStartResponse(BaseModel):
    provider: str
    auth_url: str
    state: str


class OAuthExchangeRequest(BaseModel):
    code: str
    state: str
    code_verifier: str
    device_id: str | None = None


class TokenResponse(BaseModel):
    user_id: str
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    email: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str
