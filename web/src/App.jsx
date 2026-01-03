import React, { useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:9000";
const TABS = ["Reader", "Search", "Chat"];
const CACHE_INDEX_KEY = "chapter_cache_index";
const MAX_CACHE_CHAPTERS = 200;

const cacheKey = (versionId, bookId, chapter) =>
  `chapter:${versionId}:${bookId}:${chapter}`;

const loadCacheIndex = () => {
  const raw = localStorage.getItem(CACHE_INDEX_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const saveCacheIndex = (items) => {
  localStorage.setItem(CACHE_INDEX_KEY, JSON.stringify(items));
};

const touchCacheKey = (key) => {
  const items = loadCacheIndex().filter((item) => item !== key);
  items.push(key);
  while (items.length > MAX_CACHE_CHAPTERS) {
    const evicted = items.shift();
    if (evicted) localStorage.removeItem(evicted);
  }
  saveCacheIndex(items);
};

const getCachedChapter = (versionId, bookId, chapter) => {
  const key = cacheKey(versionId, bookId, chapter);
  const raw = localStorage.getItem(key);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    touchCacheKey(key);
    return parsed;
  } catch {
    return null;
  }
};

const setCachedChapter = (versionId, bookId, chapter, payload) => {
  const key = cacheKey(versionId, bookId, chapter);
  const record = { ...payload, cached_at: new Date().toISOString() };
  localStorage.setItem(key, JSON.stringify(record));
  touchCacheKey(key);
};

export default function App() {
  const [activeTab, setActiveTab] = useState("Reader");
  const [versionId, setVersionId] = useState("krv");

  const [books, setBooks] = useState([]);
  const [booksError, setBooksError] = useState("");
  const [selectedBookId, setSelectedBookId] = useState(1);
  const [chapter, setChapter] = useState(1);
  const [chapterData, setChapterData] = useState(null);
  const [chapterError, setChapterError] = useState("");
  const [chapterNotice, setChapterNotice] = useState("");
  const [chapterLoading, setChapterLoading] = useState(false);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [searchError, setSearchError] = useState("");
  const [searchLoading, setSearchLoading] = useState(false);

  const [conversationId, setConversationId] = useState("");
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState([]);
  const [chatError, setChatError] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  const selectedBook = useMemo(
    () => books.find((book) => book.book_id === Number(selectedBookId)),
    [books, selectedBookId]
  );

  useEffect(() => {
    let cancelled = false;
    const loadBooks = async () => {
      setBooksError("");
      try {
        const res = await fetch(`${API_BASE}/v1/bible/${versionId}/books`);
        if (!res.ok) throw new Error("책 목록을 불러오지 못했습니다.");
        const data = await res.json();
        if (!cancelled) {
          setBooks(data.items || []);
          if (data.items && data.items.length > 0) {
            setSelectedBookId(data.items[0].book_id);
          }
        }
      } catch (err) {
        if (!cancelled) setBooksError(String(err.message || err));
      }
    };
    loadBooks();
    return () => {
      cancelled = true;
    };
  }, [versionId]);

  const loadChapter = async () => {
    setChapterError("");
    setChapterNotice("");
    setChapterLoading(true);
    const cached = getCachedChapter(versionId, selectedBookId, chapter);
    try {
      const res = await fetch(
        `${API_BASE}/v1/bible/${versionId}/books/${selectedBookId}/chapters/${chapter}`
      );
      if (!res.ok) throw new Error("장 본문을 불러오지 못했습니다.");
      const data = await res.json();
      if (cached?.content_hash && cached.content_hash !== data.content_hash) {
        setChapterNotice("본문이 업데이트되어 캐시를 갱신했습니다.");
      }
      setChapterData(data);
      setCachedChapter(versionId, selectedBookId, chapter, data);
    } catch (err) {
      if (cached) {
        setChapterData(cached);
        setChapterError("오프라인 캐시로 표시 중입니다.");
      } else {
        setChapterError(String(err.message || err));
      }
    } finally {
      setChapterLoading(false);
    }
  };

  const handleSearch = async () => {
    setSearchError("");
    setSearchLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/v1/bible/${versionId}/search?q=${encodeURIComponent(searchQuery)}`
      );
      if (!res.ok) throw new Error("검색에 실패했습니다.");
      const data = await res.json();
      setSearchResults(data.items || []);
      setSearchTotal(data.total || 0);
    } catch (err) {
      setSearchError(String(err.message || err));
    } finally {
      setSearchLoading(false);
    }
  };

  const ensureConversation = async () => {
    if (conversationId) return conversationId;
    const res = await fetch(`${API_BASE}/v1/chat/conversations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: "web", locale: "ko-KR", version_id: versionId })
    });
    if (!res.ok) throw new Error("세션 생성 실패");
    const data = await res.json();
    setConversationId(data.conversation_id);
    return data.conversation_id;
  };

  const sendMessage = async () => {
    if (!chatInput.trim()) return;
    setChatError("");
    setChatLoading(true);
    const userMessage = chatInput.trim();
    setChatInput("");
    setChatMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    try {
      const cid = await ensureConversation();
      const res = await fetch(`${API_BASE}/v1/chat/conversations/${cid}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_message: userMessage, client_context: { app_version: "web" } })
      });
      if (!res.ok) throw new Error("응답 생성 실패");
      const data = await res.json();
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.assistant_message || "" }
      ]);
    } catch (err) {
      setChatError(String(err.message || err));
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="hero">
        <div>
          <p className="eyebrow">TheBibleAI</p>
          <h1>말씀을 안전하게, 대화로 이어주는 MVP</h1>
          <p className="sub">읽기 · 검색 · 상담 인용을 하나의 흐름으로 연결합니다.</p>
        </div>
        <div className="hero-card">
          <div className="card-label">API BASE</div>
          <div className="card-value">{API_BASE}</div>
          <div className="card-meta">Version: {versionId}</div>
          {conversationId && <div className="card-meta">Session: {conversationId}</div>}
        </div>
      </header>

      <section className="tabs">
        {TABS.map((tab) => (
          <button
            key={tab}
            className={`tab ${activeTab === tab ? "active" : ""}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </section>

      <main className="panel">
        {activeTab === "Reader" && (
          <div className="grid">
            <div className="controls">
              <h2>읽기</h2>
              {booksError && <div className="error">{booksError}</div>}
              <label>
                책
                <select
                  value={selectedBookId}
                  onChange={(e) => setSelectedBookId(Number(e.target.value))}
                >
                  {books.map((book) => (
                    <option key={book.book_id} value={book.book_id}>
                      {book.ko_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                장
                <input
                  type="number"
                  min="1"
                  value={chapter}
                  onChange={(e) => setChapter(Number(e.target.value))}
                />
              </label>
              <button className="primary" onClick={loadChapter} disabled={chapterLoading}>
                {chapterLoading ? "불러오는 중" : "장 읽기"}
              </button>
              {chapterError && <div className="error">{chapterError}</div>}
              {chapterNotice && <div className="meta">{chapterNotice}</div>}
            </div>
            <div className="content">
              <div className="content-header">
                <h3>{selectedBook ? selectedBook.ko_name : ""}</h3>
                {chapterData?.content_hash && (
                  <span className="pill">Hash: {chapterData.content_hash}</span>
                )}
              </div>
              <div className="verses">
                {chapterData?.verses?.map((verse) => (
                  <p key={verse.verse}>
                    <span className="verse-num">{verse.verse}</span>
                    {verse.text}
                  </p>
                ))}
                {!chapterData && <div className="empty">장 데이터를 불러와 주세요.</div>}
              </div>
            </div>
          </div>
        )}

        {activeTab === "Search" && (
          <div className="grid">
            <div className="controls">
              <h2>검색</h2>
              <label>
                키워드
                <input
                  type="text"
                  value={searchQuery}
                  placeholder="태초, 평안, 불안"
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </label>
              <button className="primary" onClick={handleSearch} disabled={searchLoading}>
                {searchLoading ? "검색 중" : "검색"}
              </button>
              {searchError && <div className="error">{searchError}</div>}
              <div className="meta">총 {searchTotal}건</div>
            </div>
            <div className="content">
              {searchResults.length === 0 ? (
                <div className="empty">결과가 없습니다.</div>
              ) : (
                <ul className="list">
                  {searchResults.map((item, idx) => (
                    <li key={`${item.book_id}-${item.chapter}-${item.verse}-${idx}`}>
                      <div className="list-title">
                        {item.book_name} {item.chapter}:{item.verse}
                      </div>
                      <div
                        className="list-snippet"
                        dangerouslySetInnerHTML={{ __html: item.snippet || item.text }}
                      />
                      <div className="list-text">{item.text}</div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        {activeTab === "Chat" && (
          <div className="grid">
            <div className="controls">
              <h2>상담</h2>
              <label>
                메시지
                <textarea
                  value={chatInput}
                  placeholder="요즘 불안해서 잠이 안 와요"
                  onChange={(e) => setChatInput(e.target.value)}
                  rows={4}
                />
              </label>
              <button className="primary" onClick={sendMessage} disabled={chatLoading}>
                {chatLoading ? "응답 중" : "보내기"}
              </button>
              {chatError && <div className="error">{chatError}</div>}
            </div>
            <div className="content">
              <div className="chat">
                {chatMessages.length === 0 && (
                  <div className="empty">대화를 시작해 주세요.</div>
                )}
                {chatMessages.map((msg, idx) => (
                  <div
                    key={`${msg.role}-${idx}`}
                    className={`bubble ${msg.role === "user" ? "user" : "assistant"}`}
                  >
                    <span className="role">{msg.role}</span>
                    <p>{msg.content}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
