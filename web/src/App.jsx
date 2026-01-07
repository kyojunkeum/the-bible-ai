import React, { useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:9000";
const TABS = ["Reader", "Search", "Chat", "Account"];
const DEVICE_ID = "web";
const VERSION_OPTIONS = [
  { id: "krv", labelKo: "개역한글판", labelEn: "Korean (KRV)" },
  { id: "eng-web", labelKo: "WEB", labelEn: "English (WEB)" }
];
const EN_BOOK_NAME_BY_OSIS = {
  GEN: "Genesis",
  EXO: "Exodus",
  LEV: "Leviticus",
  NUM: "Numbers",
  DEU: "Deuteronomy",
  JOS: "Joshua",
  JDG: "Judges",
  RUT: "Ruth",
  "1SA": "1 Samuel",
  "2SA": "2 Samuel",
  "1KI": "1 Kings",
  "2KI": "2 Kings",
  "1CH": "1 Chronicles",
  "2CH": "2 Chronicles",
  EZR: "Ezra",
  NEH: "Nehemiah",
  EST: "Esther",
  JOB: "Job",
  PSA: "Psalms",
  PRO: "Proverbs",
  ECC: "Ecclesiastes",
  SNG: "Song of Solomon",
  ISA: "Isaiah",
  JER: "Jeremiah",
  LAM: "Lamentations",
  EZK: "Ezekiel",
  DAN: "Daniel",
  HOS: "Hosea",
  JOL: "Joel",
  AMO: "Amos",
  OBA: "Obadiah",
  JON: "Jonah",
  MIC: "Micah",
  NAM: "Nahum",
  HAB: "Habakkuk",
  ZEP: "Zephaniah",
  HAG: "Haggai",
  ZEC: "Zechariah",
  MAL: "Malachi",
  MAT: "Matthew",
  MRK: "Mark",
  LUK: "Luke",
  JHN: "John",
  ACT: "Acts",
  ROM: "Romans",
  "1CO": "1 Corinthians",
  "2CO": "2 Corinthians",
  GAL: "Galatians",
  EPH: "Ephesians",
  PHP: "Philippians",
  COL: "Colossians",
  "1TH": "1 Thessalonians",
  "2TH": "2 Thessalonians",
  "1TI": "1 Timothy",
  "2TI": "2 Timothy",
  TIT: "Titus",
  PHM: "Philemon",
  HEB: "Hebrews",
  JAS: "James",
  "1PE": "1 Peter",
  "2PE": "2 Peter",
  "1JN": "1 John",
  "2JN": "2 John",
  "3JN": "3 John",
  JUD: "Jude",
  REV: "Revelation"
};
const CACHE_INDEX_KEY = "chapter_cache_index";
const MAX_CACHE_CHAPTERS = 200;
const AUTH_TOKEN_KEY = "auth_token";
const AUTH_USER_KEY = "auth_user_id";
const AUTH_EMAIL_KEY = "auth_email";

const readLocal = (key) => {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(key) || "";
};

const cacheKey = (versionId, bookId, chapter) =>
  `chapter:${versionId}:${bookId}:${chapter}`;

const makeVerseKey = (bookId, chapter, verse) => `${bookId}:${chapter}:${verse}`;

const getBookDisplayName = (book, versionId) => {
  if (!book) return "";
  if (versionId !== "eng-web") {
    return book.ko_name || book.abbr || book.osis_code || "";
  }
  return (
    EN_BOOK_NAME_BY_OSIS[book.osis_code] ||
    book.ko_name ||
    book.abbr ||
    book.osis_code ||
    ""
  );
};

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
  const browserLocale =
    typeof navigator !== "undefined" && navigator.language ? navigator.language : "ko-KR";
  const isEnglishVersion = versionId === "eng-web";
  const t = (en, ko) => (isEnglishVersion ? en : ko);
  const versionOptions = useMemo(
    () =>
      VERSION_OPTIONS.map((version) => ({
        ...version,
        label: isEnglishVersion ? version.labelEn : version.labelKo
      })),
    [isEnglishVersion]
  );
  const selectedVersion = useMemo(
    () =>
      versionOptions.find((version) => version.id === versionId) || {
        id: versionId,
        label: versionId
      },
    [versionId, versionOptions]
  );

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

  const [authEmail, setAuthEmail] = useState(readLocal(AUTH_EMAIL_KEY));
  const [authPassword, setAuthPassword] = useState("");
  const [authCaptcha, setAuthCaptcha] = useState("");
  const [authUserId, setAuthUserId] = useState(readLocal(AUTH_USER_KEY));
  const [authToken, setAuthToken] = useState(readLocal(AUTH_TOKEN_KEY));
  const [authError, setAuthError] = useState("");
  const [authNotice, setAuthNotice] = useState("");
  const [authLoading, setAuthLoading] = useState(false);

  const [bookmarks, setBookmarks] = useState([]);
  const [bookmarksError, setBookmarksError] = useState("");
  const [bookmarksLoading, setBookmarksLoading] = useState(false);
  const [memos, setMemos] = useState([]);
  const [memosError, setMemosError] = useState("");
  const [memosLoading, setMemosLoading] = useState(false);
  const [openMemoKey, setOpenMemoKey] = useState("");
  const [memoDrafts, setMemoDrafts] = useState({});
  const [memoSavingKey, setMemoSavingKey] = useState("");
  const [activeVerseKey, setActiveVerseKey] = useState("");

  const selectedBook = useMemo(
    () => books.find((book) => book.book_id === Number(selectedBookId)),
    [books, selectedBookId]
  );
  const selectedBookName = useMemo(
    () => getBookDisplayName(selectedBook, versionId),
    [selectedBook, versionId]
  );
  const booksById = useMemo(
    () => new Map(books.map((book) => [book.book_id, book])),
    [books]
  );
  const getResultBookName = (item) => {
    const book = booksById.get(item.book_id);
    return getBookDisplayName(book, versionId) || item.book_name;
  };
  const getBookmarkBookName = (item) => {
    const book = booksById.get(item.book_id);
    return getBookDisplayName(book, versionId) || item.book_name;
  };
  const bookmarksByKey = useMemo(
    () => new Set(bookmarks.map((item) => makeVerseKey(item.book_id, item.chapter, item.verse))),
    [bookmarks]
  );
  const memosByKey = useMemo(() => {
    const map = new Map();
    memos.forEach((item) => {
      map.set(makeVerseKey(item.book_id, item.chapter, item.verse), item);
    });
    return map;
  }, [memos]);

  useEffect(() => {
    let cancelled = false;
    const loadBooks = async () => {
      setBooksError("");
      try {
        const res = await fetch(`${API_BASE}/v1/bible/${versionId}/books`);
        if (!res.ok) throw new Error(t("Failed to load books.", "책 목록을 불러오지 못했습니다."));
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

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (authToken) {
      localStorage.setItem(AUTH_TOKEN_KEY, authToken);
    } else {
      localStorage.removeItem(AUTH_TOKEN_KEY);
    }
    if (authUserId) {
      localStorage.setItem(AUTH_USER_KEY, authUserId);
    } else {
      localStorage.removeItem(AUTH_USER_KEY);
    }
    if (authEmail) {
      localStorage.setItem(AUTH_EMAIL_KEY, authEmail);
    } else {
      localStorage.removeItem(AUTH_EMAIL_KEY);
    }
  }, [authToken, authUserId, authEmail]);

  useEffect(() => {
    setOpenMemoKey("");
    setMemoDrafts({});
    setActiveVerseKey("");
  }, [versionId, selectedBookId, chapter]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const handleSelection = () => {
      const selection = window.getSelection();
      if (!selection) return;
      const activeElement = document.activeElement;
      if (
        activeElement &&
        (activeElement.tagName === "TEXTAREA" || activeElement.tagName === "INPUT")
      ) {
        return;
      }
      if (selection.isCollapsed || !selection.toString().trim()) {
        if (!openMemoKey) {
          setActiveVerseKey("");
        }
        return;
      }
      const anchorNode = selection.anchorNode;
      const anchorElement =
        anchorNode?.nodeType === 1 ? anchorNode : anchorNode?.parentElement;
      const verseRow = anchorElement?.closest?.(".verse-row");
      if (!verseRow) {
        setActiveVerseKey("");
        return;
      }
      const verseKey = verseRow.getAttribute("data-verse-key");
      setActiveVerseKey(verseKey || "");
    };
    document.addEventListener("selectionchange", handleSelection);
    return () => {
      document.removeEventListener("selectionchange", handleSelection);
    };
  }, [openMemoKey]);

  useEffect(() => {
    if (activeTab !== "Reader") return;
    if (!authToken) {
      setBookmarks([]);
      setMemos([]);
      return;
    }
    const loadBookmarks = async () => {
      setBookmarksError("");
      setBookmarksLoading(true);
      try {
        const params = new URLSearchParams({
          version_id: versionId,
          limit: "200"
        });
        const res = await fetch(`${API_BASE}/v1/bible/bookmarks?${params.toString()}`, {
          headers: { Authorization: `Bearer ${authToken}` }
        });
        if (!res.ok) throw new Error(t("Failed to load bookmarks.", "북마크를 불러오지 못했습니다."));
        const data = await res.json();
        setBookmarks(data.items || []);
      } catch (err) {
        setBookmarksError(String(err.message || err));
      } finally {
        setBookmarksLoading(false);
      }
    };
    const loadMemos = async () => {
      setMemosError("");
      setMemosLoading(true);
      try {
        const params = new URLSearchParams({
          version_id: versionId,
          limit: "200"
        });
        const res = await fetch(`${API_BASE}/v1/bible/memos?${params.toString()}`, {
          headers: { Authorization: `Bearer ${authToken}` }
        });
        if (!res.ok) throw new Error(t("Failed to load memos.", "메모를 불러오지 못했습니다."));
        const data = await res.json();
        setMemos(data.items || []);
      } catch (err) {
        setMemosError(String(err.message || err));
      } finally {
        setMemosLoading(false);
      }
    };
    loadBookmarks();
    loadMemos();
  }, [activeTab, versionId, authToken]);

  const loadChapter = async (override) => {
    setChapterError("");
    setChapterNotice("");
    setChapterLoading(true);
    const targetBookId =
      override?.bookId !== undefined ? Number(override.bookId) : Number(selectedBookId);
    const targetChapter =
      override?.chapter !== undefined ? Number(override.chapter) : Number(chapter);
    if (override?.bookId !== undefined) {
      setSelectedBookId(targetBookId);
    }
    if (override?.chapter !== undefined) {
      setChapter(targetChapter);
    }
    const cached = getCachedChapter(versionId, targetBookId, targetChapter);
    try {
      const res = await fetch(
        `${API_BASE}/v1/bible/${versionId}/books/${targetBookId}/chapters/${targetChapter}`
      );
      if (!res.ok) throw new Error(t("Failed to load chapter.", "장 본문을 불러오지 못했습니다."));
      const data = await res.json();
      if (cached?.content_hash && cached.content_hash !== data.content_hash) {
        setChapterNotice(
          t("Content updated; cache refreshed.", "본문이 업데이트되어 캐시를 갱신했습니다.")
        );
      }
      setChapterData(data);
      setCachedChapter(versionId, targetBookId, targetChapter, data);
    } catch (err) {
      if (cached) {
        setChapterData(cached);
        setChapterError(t("Showing offline cache.", "오프라인 캐시로 표시 중입니다."));
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
      if (!res.ok) throw new Error(t("Search failed.", "검색에 실패했습니다."));
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
      body: JSON.stringify({ device_id: DEVICE_ID, locale: browserLocale, version_id: versionId })
    });
    if (!res.ok) throw new Error(t("Failed to create session.", "세션 생성 실패"));
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
      if (!res.ok) throw new Error(t("Failed to generate response.", "응답 생성 실패"));
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

  const refreshBookmarks = async () => {
    if (!authToken) {
      setBookmarks([]);
      return;
    }
    setBookmarksError("");
    try {
      const params = new URLSearchParams({
        version_id: versionId,
        limit: "200"
      });
      const res = await fetch(`${API_BASE}/v1/bible/bookmarks?${params.toString()}`, {
        headers: { Authorization: `Bearer ${authToken}` }
      });
      if (!res.ok) throw new Error(t("Failed to load bookmarks.", "북마크를 불러오지 못했습니다."));
      const data = await res.json();
      setBookmarks(data.items || []);
    } catch (err) {
      setBookmarksError(String(err.message || err));
    }
  };

  const refreshMemos = async () => {
    if (!authToken) {
      setMemos([]);
      return;
    }
    setMemosError("");
    try {
      const params = new URLSearchParams({
        version_id: versionId,
        limit: "200"
      });
      const res = await fetch(`${API_BASE}/v1/bible/memos?${params.toString()}`, {
        headers: { Authorization: `Bearer ${authToken}` }
      });
      if (!res.ok) throw new Error(t("Failed to load memos.", "메모를 불러오지 못했습니다."));
      const data = await res.json();
      setMemos(data.items || []);
    } catch (err) {
      setMemosError(String(err.message || err));
    }
  };

  const toggleBookmark = async (bookId, verse) => {
    if (!authToken) {
      setBookmarksError(t("Sign in to use bookmarks.", "로그인 후 북마크를 사용할 수 있습니다."));
      return;
    }
    const key = makeVerseKey(bookId, chapter, verse);
    const isBookmarked = bookmarksByKey.has(key);
    setBookmarksError("");
    try {
      if (isBookmarked) {
        const params = new URLSearchParams({
          version_id: versionId,
          book_id: String(bookId),
          chapter: String(chapter),
          verse: String(verse)
        });
        const res = await fetch(`${API_BASE}/v1/bible/bookmarks?${params.toString()}`, {
          method: "DELETE",
          headers: { Authorization: `Bearer ${authToken}` }
        });
        if (!res.ok) throw new Error(t("Failed to remove bookmark.", "북마크 해제에 실패했습니다."));
      } else {
        const res = await fetch(`${API_BASE}/v1/bible/bookmarks`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${authToken}`
          },
          body: JSON.stringify({
            version_id: versionId,
            book_id: bookId,
            chapter: Number(chapter),
            verse
          })
        });
        if (!res.ok) throw new Error(t("Failed to save bookmark.", "북마크 저장에 실패했습니다."));
      }
      await refreshBookmarks();
    } catch (err) {
      setBookmarksError(String(err.message || err));
    }
  };

  const openMemoEditor = (key, memoText) => {
    setOpenMemoKey(key);
    setMemosError("");
    setMemoDrafts((prev) => ({
      ...prev,
      [key]: prev[key] ?? memoText ?? ""
    }));
    setActiveVerseKey(key);
  };

  const saveMemo = async (bookId, verse) => {
    if (!authToken) {
      setMemosError(t("Sign in to use memos.", "로그인 후 메모를 사용할 수 있습니다."));
      return;
    }
    const key = makeVerseKey(bookId, chapter, verse);
    const memoText = (memoDrafts[key] || "").trim();
    if (!memoText) {
      setMemosError(t("Please enter a memo.", "메모를 입력해주세요."));
      return;
    }
    setMemoSavingKey(key);
    setMemosError("");
    try {
      const res = await fetch(`${API_BASE}/v1/bible/memos`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`
        },
        body: JSON.stringify({
          version_id: versionId,
          book_id: bookId,
          chapter: Number(chapter),
          verse,
          memo_text: memoText
        })
      });
      if (!res.ok) throw new Error(t("Failed to save memo.", "메모 저장에 실패했습니다."));
      setOpenMemoKey("");
      await refreshMemos();
    } catch (err) {
      setMemosError(String(err.message || err));
    } finally {
      setMemoSavingKey("");
    }
  };

  const deleteMemo = async (bookId, verse) => {
    if (!authToken) {
      setMemosError(t("Sign in to use memos.", "로그인 후 메모를 사용할 수 있습니다."));
      return;
    }
    const key = makeVerseKey(bookId, chapter, verse);
    setMemoSavingKey(key);
    setMemosError("");
    try {
      const params = new URLSearchParams({
        version_id: versionId,
        book_id: String(bookId),
        chapter: String(chapter),
        verse: String(verse)
      });
      const res = await fetch(`${API_BASE}/v1/bible/memos?${params.toString()}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${authToken}` }
      });
      if (!res.ok) throw new Error(t("Failed to delete memo.", "메모 삭제에 실패했습니다."));
      setOpenMemoKey("");
      await refreshMemos();
    } catch (err) {
      setMemosError(String(err.message || err));
    } finally {
      setMemoSavingKey("");
    }
  };

  const handleRegister = async () => {
    setAuthError("");
    setAuthNotice("");
    setAuthLoading(true);
    try {
      const res = await fetch(`${API_BASE}/v1/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: authEmail,
          password: authPassword,
          device_id: DEVICE_ID
        })
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const message = data?.error?.message || t("Sign-up failed.", "회원가입에 실패했습니다.");
        throw new Error(message);
      }
      const data = await res.json();
      setAuthToken(data.session_token || "");
      setAuthUserId(data.user_id || "");
      setAuthPassword("");
      setAuthCaptcha("");
      setAuthNotice(t("Signed up and logged in.", "회원가입 및 로그인 완료"));
    } catch (err) {
      setAuthError(String(err.message || err));
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogin = async () => {
    setAuthError("");
    setAuthNotice("");
    setAuthLoading(true);
    try {
      const res = await fetch(`${API_BASE}/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: authEmail,
          password: authPassword,
          captcha_token: authCaptcha || undefined,
          device_id: DEVICE_ID
        })
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const message = data?.error?.message || t("Login failed.", "로그인에 실패했습니다.");
        throw new Error(message);
      }
      const data = await res.json();
      setAuthToken(data.session_token || "");
      setAuthUserId(data.user_id || "");
      setAuthPassword("");
      setAuthCaptcha("");
      setAuthNotice(t("Logged in.", "로그인 완료"));
    } catch (err) {
      setAuthError(String(err.message || err));
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = async () => {
    setAuthError("");
    setAuthNotice("");
    setAuthLoading(true);
    try {
      if (authToken) {
        await fetch(`${API_BASE}/v1/auth/logout`, {
          method: "POST",
          headers: { Authorization: `Bearer ${authToken}` }
        });
      }
      setAuthToken("");
      setAuthUserId("");
      setAuthPassword("");
      setAuthCaptcha("");
      setBookmarks([]);
      setMemos([]);
      setAuthNotice(t("Logged out.", "로그아웃 완료"));
    } catch (err) {
      setAuthError(String(err.message || err));
    } finally {
      setAuthLoading(false);
    }
  };

  const jumpToBookmark = (item) => {
    const verseKey = makeVerseKey(item.book_id, item.chapter, item.verse);
    setActiveTab("Reader");
    setActiveVerseKey(verseKey);
    loadChapter({ bookId: item.book_id, chapter: item.chapter });
  };

  return (
    <div className="app">
      <header className="hero">
        <div>
          <p className="eyebrow">TheBibleAI</p>
          <h1>
            {t(
              "Safe scripture, guided through conversation",
              "말씀을 안전하게, 대화로 이어주는 MVP"
            )}
          </h1>
          <p className="sub">
            {t(
              "Reader · Search · Counseling citations in one flow.",
              "읽기 · 검색 · 상담 인용을 하나의 흐름으로 연결합니다."
            )}
          </p>
        </div>
        <div className="hero-card">
          <div className="card-label">API BASE</div>
          <div className="card-value">{API_BASE}</div>
          <div className="card-meta">Version: {selectedVersion.label}</div>
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
              <h2>{t("Reader", "읽기")}</h2>
              {booksError && <div className="error">{booksError}</div>}
              <label>
                {t("Version", "버전")}
                <select value={versionId} onChange={(e) => setVersionId(e.target.value)}>
                  {versionOptions.map((version) => (
                    <option key={version.id} value={version.id}>
                      {version.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("Book", "책")}
                <select
                  value={selectedBookId}
                  onChange={(e) => setSelectedBookId(Number(e.target.value))}
                >
                  {books.map((book) => (
                    <option key={book.book_id} value={book.book_id}>
                      {getBookDisplayName(book, versionId)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("Chapter", "장")}
                <input
                  type="number"
                  min="1"
                  value={chapter}
                  onChange={(e) => setChapter(Number(e.target.value))}
                />
              </label>
              <button className="primary" onClick={loadChapter} disabled={chapterLoading}>
                {chapterLoading
                  ? t("Loading", "불러오는 중")
                  : t("Read chapter", "장 읽기")}
              </button>
              {chapterError && <div className="error">{chapterError}</div>}
              {chapterNotice && <div className="meta">{chapterNotice}</div>}
              <div className="meta">
                {t(
                  "Select a verse to reveal bookmark and memo actions.",
                  "구절을 드래그하면 북마크/메모 메뉴가 나타납니다."
                )}
              </div>
              <div className="meta-row">
                <span className="meta">
                  {bookmarksLoading || memosLoading
                    ? t("Loading bookmarks/memos", "북마크/메모 불러오는 중")
                    : t(
                        `Bookmarks ${bookmarks.length} · Memos ${memos.length}`,
                        `북마크 ${bookmarks.length} · 메모 ${memos.length}`
                      )}
                </span>
              </div>
              {!authToken && (
                <div className="meta">
                  {t(
                    "Sign in to use bookmarks and memos.",
                    "북마크/메모는 로그인 후 사용할 수 있습니다."
                  )}
                </div>
              )}
              {bookmarksError && <div className="error">{bookmarksError}</div>}
              {memosError && <div className="error">{memosError}</div>}
              {authToken && (
                <div className="bookmark-panel">
                  <div className="bookmark-header">
                    <div className="bookmark-title">{t("Bookmarks", "북마크")}</div>
                    <button className="ghost small" onClick={refreshBookmarks}>
                      {t("Refresh", "새로고침")}
                    </button>
                  </div>
                  {bookmarks.length === 0 ? (
                    <div className="meta">
                      {t("No bookmarks yet.", "북마크가 없습니다.")}
                    </div>
                  ) : (
                    <ul className="bookmark-list">
                      {bookmarks.map((item) => (
                        <li
                          key={`${item.book_id}-${item.chapter}-${item.verse}`}
                          className="bookmark-item"
                        >
                          <div className="bookmark-text">
                            {getBookmarkBookName(item)} {item.chapter}:{item.verse}
                          </div>
                          <button
                            className="ghost small"
                            onClick={() => jumpToBookmark(item)}
                          >
                            {t("Open", "열기")}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
            <div className="content">
              <div className="content-header">
                <h3>{selectedBookName}</h3>
                {chapterData?.content_hash && (
                  <span className="pill">Hash: {chapterData.content_hash}</span>
                )}
              </div>
              <div className="verses">
                {chapterData?.verses?.map((verse) => {
                  const verseKey = makeVerseKey(selectedBookId, chapter, verse.verse);
                  const isActive = activeVerseKey === verseKey;
                  const bookmarkLabel = isEnglishVersion
                    ? bookmarksByKey.has(verseKey)
                      ? "Bookmarked"
                      : "Bookmark"
                    : bookmarksByKey.has(verseKey)
                      ? "북마크됨"
                      : "북마크";
                  const memoLabel = isEnglishVersion
                    ? memosByKey.has(verseKey)
                      ? "Edit memo"
                      : "Memo"
                    : memosByKey.has(verseKey)
                      ? "메모 수정"
                      : "메모";
                  const closeLabel = isEnglishVersion ? "Close" : "닫기";
                  return (
                  <div
                    key={verse.verse}
                    className={`verse-row ${isActive ? "active" : ""}`}
                    data-verse-key={verseKey}
                  >
                    <div className="verse-text">
                      <span className="verse-num">{verse.verse}</span>
                      {verse.text}
                    </div>
                    {isActive && (
                      <div className="verse-actions">
                        <button
                          type="button"
                          className={`verse-action ${
                            bookmarksByKey.has(verseKey) ? "active" : ""
                          }`}
                          onClick={() => toggleBookmark(selectedBookId, verse.verse)}
                          disabled={!authToken}
                        >
                          {bookmarkLabel}
                        </button>
                        <button
                          type="button"
                          className={`verse-action ${
                            memosByKey.has(verseKey) ? "active" : ""
                          }`}
                          onClick={() =>
                            openMemoEditor(verseKey, memosByKey.get(verseKey)?.memo_text)
                          }
                          disabled={!authToken}
                        >
                          {memoLabel}
                        </button>
                      </div>
                    )}
                    {openMemoKey ===
                      makeVerseKey(selectedBookId, chapter, verse.verse) && (
                      <div className="memo-editor">
                        <textarea
                          rows={3}
                          placeholder={t(
                            "Leave a note for this verse.",
                            "이 절에 대한 메모를 남겨보세요."
                          )}
                          value={
                            memoDrafts[
                              makeVerseKey(selectedBookId, chapter, verse.verse)
                            ] || ""
                          }
                          onChange={(e) =>
                            setMemoDrafts((prev) => ({
                              ...prev,
                              [makeVerseKey(selectedBookId, chapter, verse.verse)]: e.target.value
                            }))
                          }
                        />
                        <div className="memo-actions">
                          <button
                            className="primary"
                            onClick={() => saveMemo(selectedBookId, verse.verse)}
                            disabled={
                              !authToken ||
                              memoSavingKey ===
                              makeVerseKey(selectedBookId, chapter, verse.verse)
                            }
                          >
                            {memoSavingKey ===
                            makeVerseKey(selectedBookId, chapter, verse.verse)
                              ? t("Saving", "저장 중")
                              : t("Save", "저장")}
                          </button>
                          {memosByKey.has(
                            makeVerseKey(selectedBookId, chapter, verse.verse)
                          ) && (
                            <button
                              className="ghost"
                              onClick={() => deleteMemo(selectedBookId, verse.verse)}
                              disabled={
                                !authToken ||
                                memoSavingKey ===
                                makeVerseKey(selectedBookId, chapter, verse.verse)
                              }
                            >
                              {t("Delete", "삭제")}
                            </button>
                          )}
                          <button
                            className="ghost"
                            onClick={() => setOpenMemoKey("")}
                          >
                            {closeLabel}
                          </button>
                        </div>
                      </div>
                    )}
                    {isActive &&
                      openMemoKey !==
                        makeVerseKey(selectedBookId, chapter, verse.verse) &&
                      memosByKey.has(
                        makeVerseKey(selectedBookId, chapter, verse.verse)
                      ) && (
                        <div className="memo-view">
                          {t("Memo:", "메모:")}{" "}
                          {
                            memosByKey.get(
                              makeVerseKey(selectedBookId, chapter, verse.verse)
                            )?.memo_text
                          }
                        </div>
                      )}
                  </div>
                );
                })}
                {!chapterData && (
                  <div className="empty">
                    {t("Please load a chapter.", "장 데이터를 불러와 주세요.")}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === "Search" && (
          <div className="grid">
            <div className="controls">
              <h2>{t("Search", "검색")}</h2>
              <label>
                {t("Version", "버전")}
                <select value={versionId} onChange={(e) => setVersionId(e.target.value)}>
                  {versionOptions.map((version) => (
                    <option key={version.id} value={version.id}>
                      {version.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("Keyword", "키워드")}
                <input
                  type="text"
                  value={searchQuery}
                  placeholder={t("Genesis, peace, anxiety", "태초, 평안, 불안")}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </label>
              <button className="primary" onClick={handleSearch} disabled={searchLoading}>
                {searchLoading ? t("Searching", "검색 중") : t("Search", "검색")}
              </button>
              {searchError && <div className="error">{searchError}</div>}
              <div className="meta">
                {t(`Total ${searchTotal}`, `총 ${searchTotal}건`)}
              </div>
            </div>
            <div className="content">
              {searchResults.length === 0 ? (
                <div className="empty">{t("No results found.", "결과가 없습니다.")}</div>
              ) : (
                <ul className="list">
                  {searchResults.map((item, idx) => (
                    <li key={`${item.book_id}-${item.chapter}-${item.verse}-${idx}`}>
                      <div className="list-title">
                        {getResultBookName(item)} {item.chapter}:{item.verse}
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
              <h2>{t("Counseling", "상담")}</h2>
              <label>
                {t("Message", "메시지")}
                <textarea
                  value={chatInput}
                  placeholder={t(
                    "I'm anxious and can't sleep lately.",
                    "요즘 불안해서 잠이 안 와요"
                  )}
                  onChange={(e) => setChatInput(e.target.value)}
                  rows={4}
                />
              </label>
              <button className="primary" onClick={sendMessage} disabled={chatLoading}>
                {chatLoading ? t("Responding", "응답 중") : t("Send", "보내기")}
              </button>
              {chatError && <div className="error">{chatError}</div>}
            </div>
            <div className="content">
              <div className="chat">
                {chatMessages.length === 0 && (
                  <div className="empty">{t("Start a conversation.", "대화를 시작해 주세요.")}</div>
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

        {activeTab === "Account" && (
          <div className="grid">
            <div className="controls">
              <h2>{t("Account", "계정")}</h2>
              <label>
                {t("Email", "이메일")}
                <input
                  type="email"
                  value={authEmail}
                  placeholder="you@example.com"
                  onChange={(e) => setAuthEmail(e.target.value)}
                />
              </label>
              <label>
                {t("Password", "비밀번호")}
                <input
                  type="password"
                  value={authPassword}
                  placeholder={t(
                    "At least 12 characters (max 128)",
                    "12자 이상 (최대 128자)"
                  )}
                  onChange={(e) => setAuthPassword(e.target.value)}
                />
              </label>
              <label>
                {t("Captcha token (if required)", "추가 인증 토큰 (필요 시)")}
                <input
                  type="text"
                  value={authCaptcha}
                  placeholder="captcha_token"
                  onChange={(e) => setAuthCaptcha(e.target.value)}
                />
              </label>
              <button
                className="primary"
                onClick={handleLogin}
                disabled={authLoading || !authEmail || !authPassword}
              >
                {authLoading ? t("Working", "처리 중") : t("Sign in", "로그인")}
              </button>
              <button
                className="ghost"
                onClick={handleRegister}
                disabled={authLoading || !authEmail || !authPassword}
              >
                {t("Create account", "회원가입")}
              </button>
              {authError && <div className="error">{authError}</div>}
              {authNotice && <div className="meta">{authNotice}</div>}
            </div>
            <div className="content">
              <div className="content-header">
                <h3>{t("Status", "상태")}</h3>
              </div>
              {authToken ? (
                <div className="list">
                  <div>
                    <div className="list-title">{t("Signed in", "로그인됨")}</div>
                    <div className="list-text">User: {authUserId}</div>
                    <div className="list-text">Email: {authEmail}</div>
                  </div>
                  <button className="ghost" onClick={handleLogout} disabled={authLoading}>
                    {t("Sign out", "로그아웃")}
                  </button>
                </div>
              ) : (
                <div className="empty">
                  {t(
                    "Sign in to save bookmarks and memos to your account.",
                    "로그인하면 북마크/메모가 계정별로 저장됩니다."
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
