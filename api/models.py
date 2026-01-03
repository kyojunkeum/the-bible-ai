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
