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
