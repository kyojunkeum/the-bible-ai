import React, { useEffect, useMemo, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:9000";
const GOOGLE_OAUTH_ENABLED =
  import.meta.env.VITE_GOOGLE_OAUTH_ENABLED === "1" ||
  Boolean(import.meta.env.VITE_GOOGLE_CLIENT_ID);
const TABS = ["Reader", "Search", "Chat", "Account"];
const DEVICE_ID_KEY = "device_id";
const getOrCreateDeviceId = () => {
  if (typeof window === "undefined") return "web";
  const existing = localStorage.getItem(DEVICE_ID_KEY);
  if (existing) return existing;
  let nextId = "";
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    nextId = crypto.randomUUID();
  } else {
    nextId = `web_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
  }
  localStorage.setItem(DEVICE_ID_KEY, nextId);
  return nextId;
};
const DEVICE_ID = getOrCreateDeviceId();
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
const AUTH_REFRESH_KEY = "auth_refresh_token";
const AUTH_USER_KEY = "auth_user_id";
const AUTH_EMAIL_KEY = "auth_email";
const VERSE_FONT_SIZE_KEY = "verse_font_size";
const PRIVACY_NOTICE_KEY = "has_seen_privacy_notice";
const CHAT_STORAGE_CONSENT_KEY = "chat_storage_consent";
const CHAT_STORAGE_SYNC_KEY = "chat_storage_sync_applied";
const SPLASH_DURATION_MS = 5000;
const SPLASH_MESSAGE_KO =
  "평안, 말씀을 대화로, 안전하게, 읽기 검색 상담을 하나의 앱에서 경험합니다";
const SPLASH_MESSAGE_EN =
  "Peaceful scripture through conversation. Reader, search, and counseling in one app.";

const readLocal = (key) => {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(key) || "";
};

const removeLocal = (key) => {
  if (typeof window === "undefined") return;
  localStorage.removeItem(key);
};

const PKCE_VERIFIER_PREFIX = "pkce_verifier:";
const pkceVerifierKey = (state) => `${PKCE_VERIFIER_PREFIX}${state}`;

const base64UrlEncode = (bytes) => {
  const binary = String.fromCharCode(...bytes);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
};

const generateCodeVerifier = () => {
  const data = new Uint8Array(32);
  crypto.getRandomValues(data);
  return base64UrlEncode(data);
};

const buildCodeChallenge = async (verifier) => {
  const data = new TextEncoder().encode(verifier);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return base64UrlEncode(new Uint8Array(digest));
};

const readLocalBool = (key, fallback = false) => {
  const raw = readLocal(key);
  if (!raw) return fallback;
  return raw === "true";
};

const readFontSize = () => {
  const raw = readLocal(VERSE_FONT_SIZE_KEY);
  const parsed = Number(raw);
  if (Number.isFinite(parsed) && parsed >= 14 && parsed <= 32) {
    return parsed;
  }
  return 18;
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
  const [showSplash, setShowSplash] = useState(true);
  const [verseFontSize, setVerseFontSize] = useState(readFontSize);
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
  const [chatLimitReason, setChatLimitReason] = useState("");

  const [authEmail, setAuthEmail] = useState(readLocal(AUTH_EMAIL_KEY));
  const [authPassword, setAuthPassword] = useState("");
  const [authCaptcha, setAuthCaptcha] = useState("");
  const [authUserId, setAuthUserId] = useState(readLocal(AUTH_USER_KEY));
  const [authToken, setAuthToken] = useState(readLocal(AUTH_TOKEN_KEY));
  const [authRefreshToken, setAuthRefreshToken] = useState(readLocal(AUTH_REFRESH_KEY));
  const [authError, setAuthError] = useState("");
  const [authNotice, setAuthNotice] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [oauthError, setOauthError] = useState("");
  const [oauthLoading, setOauthLoading] = useState(false);
  const [chatStorageConsent, setChatStorageConsent] = useState(
    readLocalBool(CHAT_STORAGE_CONSENT_KEY, false)
  );
  const [chatStorageSynced, setChatStorageSynced] = useState(
    readLocalBool(CHAT_STORAGE_SYNC_KEY, false)
  );
  const [showPrivacyNotice, setShowPrivacyNotice] = useState(false);
  const [showStorageConfirm, setShowStorageConfirm] = useState(false);
  const [settingsError, setSettingsError] = useState("");
  const [settingsNotice, setSettingsNotice] = useState("");
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [serverStoreMessages, setServerStoreMessages] = useState(null);
  const [openaiEnabled, setOpenaiEnabled] = useState(false);
  const [openaiKeySet, setOpenaiKeySet] = useState(false);
  const [openaiKeyInput, setOpenaiKeyInput] = useState("");
  const [openaiSettingsError, setOpenaiSettingsError] = useState("");
  const [openaiSettingsNotice, setOpenaiSettingsNotice] = useState("");
  const [openaiSettingsLoading, setOpenaiSettingsLoading] = useState(false);
  const [chatMeta, setChatMeta] = useState(null);
  const [chatLimitReached, setChatLimitReached] = useState(false);

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
  const previousVersionRef = useRef(versionId);

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
          const items = data.items || [];
          setBooks(items);
          if (items.length > 0) {
            setSelectedBookId((prev) => {
              const numericPrev = Number(prev);
              const hasPrev = items.some((book) => book.book_id === numericPrev);
              return hasPrev ? numericPrev : items[0].book_id;
            });
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
    const timer = setTimeout(() => setShowSplash(false), SPLASH_DURATION_MS);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setShowPrivacyNotice(true);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    localStorage.setItem(VERSE_FONT_SIZE_KEY, String(verseFontSize));
  }, [verseFontSize]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    localStorage.setItem(CHAT_STORAGE_CONSENT_KEY, String(chatStorageConsent));
  }, [chatStorageConsent]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    localStorage.setItem(CHAT_STORAGE_SYNC_KEY, String(chatStorageSynced));
  }, [chatStorageSynced]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (authToken) {
      localStorage.setItem(AUTH_TOKEN_KEY, authToken);
    } else {
      localStorage.removeItem(AUTH_TOKEN_KEY);
    }
    if (authRefreshToken) {
      localStorage.setItem(AUTH_REFRESH_KEY, authRefreshToken);
    } else {
      localStorage.removeItem(AUTH_REFRESH_KEY);
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
  }, [authToken, authRefreshToken, authUserId, authEmail]);

  useEffect(() => {
    if (!authToken) {
      setServerStoreMessages(null);
      setOpenaiEnabled(false);
      setOpenaiKeySet(false);
      setOpenaiKeyInput("");
      setOpenaiSettingsError("");
      setOpenaiSettingsNotice("");
      setOpenaiSettingsLoading(false);
      setChatMeta(null);
      setConversationId("");
      setChatMessages([]);
      setChatLimitReached(false);
      setChatLimitReason("");
      setSettingsError("");
      setSettingsNotice("");
      return;
    }
    const loadSettings = async () => {
      setSettingsError("");
      setSettingsLoading(true);
      try {
        const res = await authFetch(`${API_BASE}/v1/users/me/settings`);
        if (!res.ok) throw new Error(t("Failed to load settings.", "설정 불러오기 실패"));
        const data = await res.json();
        const storeValue = Boolean(data.store_messages);
        setServerStoreMessages(storeValue);
        setOpenaiEnabled(Boolean(data.openai_citation_enabled));
        setOpenaiKeySet(Boolean(data.openai_api_key_set));
        if (!chatStorageSynced && storeValue === chatStorageConsent) {
          setChatStorageSynced(true);
        }
      } catch (err) {
        setSettingsError(String(err.message || err));
      } finally {
        setSettingsLoading(false);
      }
    };
    loadSettings();
  }, [authToken]);

  useEffect(() => {
    setOpenMemoKey("");
    setMemoDrafts({});
    setActiveVerseKey("");
  }, [selectedBookId, chapter]);

  useEffect(() => {
    if (previousVersionRef.current === versionId) return;
    previousVersionRef.current = versionId;
    if (selectedBookId && chapter) {
      loadChapter({ bookId: selectedBookId, chapter });
    }
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
        const res = await authFetch(`${API_BASE}/v1/bible/bookmarks?${params.toString()}`);
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
        const res = await authFetch(`${API_BASE}/v1/bible/memos?${params.toString()}`);
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
    const res = await authFetch(`${API_BASE}/v1/chat/conversations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_id: DEVICE_ID,
        locale: browserLocale,
        version_id: versionId,
        store_messages: chatStorageConsent
      })
    });
    if (!res.ok) throw new Error(t("Failed to create session.", "세션 생성 실패"));
    const data = await res.json();
    setConversationId(data.conversation_id);
    setChatMeta({
      mode: data.mode,
      store_messages: data.store_messages,
      expires_at: data.expires_at,
      turn_limit: data.turn_limit,
      turn_count: data.turn_count,
      remaining_turns: data.remaining_turns,
      daily_turn_limit: data.daily_turn_limit,
      daily_turn_count: data.daily_turn_count,
      daily_remaining: data.daily_remaining
    });
    setChatLimitReached(false);
    setChatLimitReason("");
    return data.conversation_id;
  };

  const sendMessage = async () => {
    if (!chatInput.trim() || chatLimitReached) return;
    setChatError("");
    setChatLoading(true);
    const userMessage = chatInput.trim();
    setChatInput("");
    setChatMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    try {
      const cid = await ensureConversation();
      const res = await authFetch(`${API_BASE}/v1/chat/conversations/${cid}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_message: userMessage, client_context: { app_version: "web" } })
      });
      if (!res.ok) {
        if (res.status === 410) {
          setConversationId("");
          setChatLimitReached(false);
          setChatLimitReason("");
          throw new Error(t("Session expired.", "세션이 만료되었습니다."));
        }
        if (res.status === 429) {
          const detail = await res
            .json()
            .then((data) => data?.error?.message || "")
            .catch(() => "");
          const isDailyLimit = detail === "daily trial limit reached";
          setChatLimitReached(true);
          setChatLimitReason(isDailyLimit ? "daily" : "trial");
          throw new Error(
            isDailyLimit
              ? t("Daily limit reached for today.", "오늘 제한이 종료되었습니다.")
              : t("Trial limit reached.", "체험 턴이 종료되었습니다.")
          );
        }
        throw new Error(t("Failed to generate response.", "응답 생성 실패"));
      }
      const data = await res.json();
      if (data.memory) {
        setChatMeta((prev) => ({
          mode: prev?.mode || (authToken ? "authenticated" : "anonymous"),
          store_messages: data.memory.store_messages ?? prev?.store_messages,
          expires_at: data.memory.expires_at ?? prev?.expires_at,
          turn_limit: data.memory.turn_limit ?? prev?.turn_limit,
          turn_count: data.memory.turn_count ?? prev?.turn_count,
          remaining_turns: data.memory.remaining_turns ?? prev?.remaining_turns,
          daily_turn_limit: data.memory.daily_turn_limit ?? prev?.daily_turn_limit,
          daily_turn_count: data.memory.daily_turn_count ?? prev?.daily_turn_count,
          daily_remaining: data.memory.daily_remaining ?? prev?.daily_remaining
        }));
      }
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
      const res = await authFetch(`${API_BASE}/v1/bible/bookmarks?${params.toString()}`);
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
      const res = await authFetch(`${API_BASE}/v1/bible/memos?${params.toString()}`);
      if (!res.ok) throw new Error(t("Failed to load memos.", "메모를 불러오지 못했습니다."));
      const data = await res.json();
      setMemos(data.items || []);
    } catch (err) {
      setMemosError(String(err.message || err));
    }
  };

  const refreshAccessToken = async () => {
    if (!authRefreshToken) return null;
    try {
      const res = await fetch(`${API_BASE}/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: authRefreshToken })
      });
      if (!res.ok) throw new Error("refresh_failed");
      const data = await res.json();
      setAuthToken(data.access_token || "");
      setAuthRefreshToken(data.refresh_token || "");
      if (data.user_id) setAuthUserId(data.user_id);
      if (data.email) setAuthEmail(data.email);
      return data.access_token || null;
    } catch {
      setAuthToken("");
      setAuthRefreshToken("");
      setAuthUserId("");
      setAuthEmail("");
      return null;
    }
  };

  const authFetch = async (url, options = {}) => {
    const headers = { ...(options.headers || {}) };
    if (authToken) {
      headers.Authorization = `Bearer ${authToken}`;
    }
    const res = await fetch(url, { ...options, headers });
    if (res.status !== 401 || !authRefreshToken) return res;
    const newToken = await refreshAccessToken();
    if (!newToken) return res;
    const retryHeaders = { ...(options.headers || {}), Authorization: `Bearer ${newToken}` };
    return fetch(url, { ...options, headers: retryHeaders });
  };

  const clearOauthQuery = () => {
    if (typeof window === "undefined") return;
    const cleanUrl = `${window.location.origin}${window.location.pathname}`;
    window.history.replaceState({}, document.title, cleanUrl);
  };

  const applyPrivacyChoice = (consentValue) => {
    setChatStorageConsent(consentValue);
    setShowPrivacyNotice(false);
    if (typeof window !== "undefined") {
      localStorage.setItem(PRIVACY_NOTICE_KEY, "true");
    }
  };

  const applyServerStoreSetting = async (nextValue, { resetConversation = false } = {}) => {
    if (!authToken) return;
    setSettingsError("");
    setSettingsNotice("");
    setSettingsLoading(true);
    try {
      const res = await authFetch(`${API_BASE}/v1/users/me/settings`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ store_messages: Boolean(nextValue) })
      });
      if (!res.ok) throw new Error(t("Failed to update settings.", "설정 변경 실패"));
      const data = await res.json();
      setServerStoreMessages(Boolean(data.store_messages));
      setChatStorageSynced(true);
      setSettingsNotice(
        nextValue
          ? t("Chat storage enabled.", "대화 저장이 켜졌습니다.")
          : t("Chat storage disabled.", "대화 저장이 꺼졌습니다.")
      );
      if (resetConversation) {
        setConversationId("");
        setChatMessages([]);
        setChatMeta(null);
        setChatLimitReached(false);
      }
    } catch (err) {
      setSettingsError(String(err.message || err));
    } finally {
      setSettingsLoading(false);
    }
  };

  const requestStoreSettingChange = (nextValue) => {
    if (!authToken) {
      setSettingsError(t("Sign in to change settings.", "로그인 후 설정할 수 있습니다."));
      return;
    }
    if (nextValue) {
      setShowStorageConfirm(true);
      return;
    }
    applyServerStoreSetting(false, { resetConversation: true });
  };

  const confirmStoreEnable = () => {
    setShowStorageConfirm(false);
    applyServerStoreSetting(true);
  };

  const syncLocalPreference = () => {
    if (chatStorageConsent) {
      requestStoreSettingChange(true);
      return;
    }
    applyServerStoreSetting(false, { resetConversation: true });
  };

  const dismissSyncPrompt = () => {
    setChatStorageSynced(true);
  };

  const applyOpenaiSettings = async (nextEnabled, { apiKey } = {}) => {
    if (!authToken) return;
    setOpenaiSettingsError("");
    setOpenaiSettingsNotice("");
    setOpenaiSettingsLoading(true);
    try {
      const payload = {
        openai_citation_enabled: Boolean(nextEnabled)
      };
      if (apiKey !== undefined) {
        payload.openai_api_key = apiKey;
      }
      const res = await authFetch(`${API_BASE}/v1/users/me/settings`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error(t("Failed to update settings.", "설정 변경 실패"));
      const data = await res.json();
      setOpenaiEnabled(Boolean(data.openai_citation_enabled));
      setOpenaiKeySet(Boolean(data.openai_api_key_set));
      if (apiKey !== undefined) {
        setOpenaiKeyInput("");
      }
      setOpenaiSettingsNotice(
        nextEnabled
          ? t("OpenAI citations enabled.", "OpenAI 인용이 켜졌습니다.")
          : t("OpenAI citations disabled.", "OpenAI 인용이 꺼졌습니다.")
      );
    } catch (err) {
      setOpenaiSettingsError(String(err.message || err));
    } finally {
      setOpenaiSettingsLoading(false);
    }
  };

  const requestOpenaiToggle = (nextEnabled) => {
    if (!authToken) {
      setOpenaiSettingsError(t("Sign in to change settings.", "로그인 후 설정할 수 있습니다."));
      return;
    }
    if (nextEnabled && !openaiKeySet && !openaiKeyInput.trim()) {
      setOpenaiSettingsError(
        t("Please add an OpenAI API key first.", "OpenAI API 키를 먼저 입력하세요.")
      );
      return;
    }
    applyOpenaiSettings(nextEnabled, {
      apiKey: openaiKeyInput.trim() ? openaiKeyInput.trim() : undefined
    });
  };

  const saveOpenaiKey = () => {
    const trimmed = openaiKeyInput.trim();
    if (!trimmed) {
      setOpenaiSettingsError(
        t("Enter an OpenAI API key to save.", "저장할 OpenAI API 키를 입력하세요.")
      );
      return;
    }
    applyOpenaiSettings(openaiEnabled, { apiKey: trimmed });
  };

  const clearOpenaiKey = () => {
    applyOpenaiSettings(false, { apiKey: "" });
  };

  const startGoogleOauth = async () => {
    if (!GOOGLE_OAUTH_ENABLED) return;
    if (typeof window === "undefined" || !crypto?.subtle) {
      setOauthError(
        t("OAuth is not supported in this browser.", "이 브라우저는 OAuth를 지원하지 않습니다.")
      );
      return;
    }
    setOauthError("");
    setOauthLoading(true);
    try {
      const verifier = generateCodeVerifier();
      const challenge = await buildCodeChallenge(verifier);
      const redirectUri = `${window.location.origin}${window.location.pathname}`;
      const res = await fetch(`${API_BASE}/v1/auth/oauth/google/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          redirect_uri: redirectUri,
          code_challenge: challenge,
          code_challenge_method: "S256",
          device_id: DEVICE_ID
        })
      });
      if (!res.ok) throw new Error(t("Google sign-in is not available.", "구글 로그인 사용 불가"));
      const data = await res.json();
      if (!data.state || !data.auth_url) {
        throw new Error(t("Google sign-in failed to start.", "구글 로그인 시작 실패"));
      }
      localStorage.setItem(pkceVerifierKey(data.state), verifier);
      window.location.assign(data.auth_url);
    } catch (err) {
      setOauthError(String(err.message || err));
      setOauthLoading(false);
    }
  };

  useEffect(() => {
    if (!GOOGLE_OAUTH_ENABLED || typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const state = params.get("state");
    const error = params.get("error");
    if (!code && !state && !error) return;
    if (error) {
      setOauthError(t("Google sign-in was canceled.", "구글 로그인이 취소되었습니다."));
      clearOauthQuery();
      return;
    }
    if (!code || !state) {
      setOauthError(
        t("Google sign-in response is incomplete.", "구글 로그인 응답이 불완전합니다.")
      );
      clearOauthQuery();
      return;
    }
    const verifier = localStorage.getItem(pkceVerifierKey(state));
    localStorage.removeItem(pkceVerifierKey(state));
    if (!verifier) {
      setOauthError(t("Google sign-in failed. Please try again.", "구글 로그인에 실패했습니다."));
      clearOauthQuery();
      return;
    }
    const exchange = async () => {
      setOauthLoading(true);
      setOauthError("");
      try {
        const res = await fetch(`${API_BASE}/v1/auth/oauth/google/exchange`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            code,
            state,
            code_verifier: verifier,
            device_id: DEVICE_ID
          })
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          const message =
            data?.error?.message || t("Google sign-in failed.", "구글 로그인에 실패했습니다.");
          throw new Error(message);
        }
        const data = await res.json();
        setAuthToken(data.access_token || "");
        setAuthRefreshToken(data.refresh_token || "");
        setAuthUserId(data.user_id || "");
        if (data.email) setAuthEmail(data.email);
        setAuthPassword("");
        setAuthCaptcha("");
        setAuthNotice(t("Logged in with Google.", "구글 로그인 완료"));
      } catch (err) {
        setOauthError(String(err.message || err));
      } finally {
        setOauthLoading(false);
        clearOauthQuery();
      }
    };
    exchange();
  }, []);

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
        const res = await authFetch(`${API_BASE}/v1/bible/bookmarks?${params.toString()}`, {
          method: "DELETE"
        });
        if (!res.ok) throw new Error(t("Failed to remove bookmark.", "북마크 해제에 실패했습니다."));
      } else {
        const res = await authFetch(`${API_BASE}/v1/bible/bookmarks`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
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
      const res = await authFetch(`${API_BASE}/v1/bible/memos`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
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
      const res = await authFetch(`${API_BASE}/v1/bible/memos?${params.toString()}`, {
        method: "DELETE"
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
      setAuthToken(data.access_token || "");
      setAuthRefreshToken(data.refresh_token || "");
      setAuthUserId(data.user_id || "");
      if (data.email) setAuthEmail(data.email);
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
      setAuthToken(data.access_token || "");
      setAuthRefreshToken(data.refresh_token || "");
      setAuthUserId(data.user_id || "");
      if (data.email) setAuthEmail(data.email);
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
      if (authRefreshToken) {
        await fetch(`${API_BASE}/v1/auth/logout`, {
          method: "POST",
          headers: { Authorization: `Bearer ${authRefreshToken}` }
        });
      }
      setAuthToken("");
      setAuthRefreshToken("");
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
      {showSplash && (
        <div className="splash-overlay">
          <div className="splash-card">
            <p className="splash-eyebrow">평안</p>
            <h1 className="splash-title">{t(SPLASH_MESSAGE_EN, SPLASH_MESSAGE_KO)}</h1>
          </div>
        </div>
      )}
      {showPrivacyNotice && !showSplash && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-title">
              {t("Chat storage notice", "대화 저장 고지")}
            </div>
            <p className="modal-text">
              {t(
                "Anonymous trial: chats are not saved and disappear when you close the app.",
                "익명 체험: 대화는 저장되지 않고 앱을 닫으면 사라집니다."
              )}
            </p>
            <p className="modal-text">
              {t(
                "Signed-in users: chats are stored only if you enable it in settings.",
                "로그인 사용자: 대화 저장은 설정에서 켠 경우에만 저장됩니다."
              )}
            </p>
            <p className="modal-text">
              {t(
                "Safety: if crisis language is detected, responses may be limited.",
                "안전: 위기 표현이 감지되면 상담이 제한되고 도움 안내가 제공될 수 있습니다."
              )}
            </p>
            <div className="modal-actions">
              <button className="primary" onClick={() => applyPrivacyChoice(true)}>
                {t("Agree and start", "동의하고 시작")}
              </button>
              <button className="ghost" onClick={() => applyPrivacyChoice(false)}>
                {t("Use without saving", "저장하지 않고 사용")}
              </button>
            </div>
            <div className="modal-footnote">
              {t("You can change this later in settings.", "언제든 설정에서 변경 가능합니다.")}
            </div>
          </div>
        </div>
      )}
      {showStorageConfirm && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-title">
              {t("Enable chat storage?", "대화 저장을 켤까요?")}
            </div>
            <p className="modal-text">
              {t(
                "Stored items: your chat messages (questions and responses).",
                "저장되는 것: 대화 내용(질문/답변)"
              )}
            </p>
            <p className="modal-text">
              {t(
                "Purpose: conversation history and service quality.",
                "목적: 대화 이력 제공 및 품질 개선"
              )}
            </p>
            <p className="modal-text">
              {t(
                "You can turn this off anytime in settings.",
                "언제든 OFF로 변경할 수 있습니다."
              )}
            </p>
            <div className="modal-actions">
              <button className="primary" onClick={confirmStoreEnable}>
                {t("Agree and turn on", "동의하고 저장 켜기")}
              </button>
              <button
                className="ghost"
                onClick={() => {
                  setShowStorageConfirm(false);
                }}
              >
                {t("Cancel", "취소")}
              </button>
            </div>
          </div>
        </div>
      )}
      <header className="hero">
        <div>
          <p className="eyebrow">평안</p>
          <h1>
            {t("평안 Platform", "평안 플랫폼")}
          </h1>
          <p className="sub">
            {t(
              "Bible reading, search, and citation-safe counseling.",
              "성경 읽기, 검색, 인용 안전 상담을 제공합니다."
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
              <label>
                {t("Text size", "본문 글자 크기")}
                <input
                  type="range"
                  min="16"
                  max="28"
                  step="1"
                  value={verseFontSize}
                  onChange={(e) => setVerseFontSize(Number(e.target.value))}
                />
                <span className="meta">{t(`${verseFontSize}px`, `${verseFontSize}px`)}</span>
              </label>
              <button className="primary" onClick={loadChapter} disabled={chapterLoading}>
                {t("Read chapter", "장 읽기")}
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
                    <div className="verse-text" style={{ fontSize: `${verseFontSize}px` }}>
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
              {(chatMeta?.mode === "anonymous" || !authToken) && (
                <div className="trial-banner">
                  <span className="pill warn">
                    {t("Anonymous trial: not saved", "익명 체험: 저장되지 않음")}
                  </span>
                  {chatMeta?.daily_turn_limit ? (
                    <span className="meta">
                      {t(
                        `Daily remaining ${chatMeta.daily_remaining ?? 0}/${chatMeta.daily_turn_limit}`,
                        `오늘 남은 턴 ${chatMeta.daily_remaining ?? 0}/${chatMeta.daily_turn_limit}`
                      )}
                    </span>
                  ) : chatMeta?.turn_limit ? (
                    <span className="meta">
                      {t(
                        `Remaining ${chatMeta.remaining_turns ?? 0}/${chatMeta.turn_limit}`,
                        `남은 턴 ${chatMeta.remaining_turns ?? 0}/${chatMeta.turn_limit}`
                      )}
                    </span>
                  ) : null}
                  <span className="meta">
                    {t(
                      "Storage options are available after sign-in.",
                      "저장 옵션은 로그인 후 설정에서 선택 가능합니다."
                    )}
                  </span>
                </div>
              )}
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
                  disabled={chatLimitReached}
                />
              </label>
              <button
                className="primary"
                onClick={sendMessage}
                disabled={chatLoading || chatLimitReached}
              >
                {chatLoading ? t("Responding", "응답 중") : t("Send", "보내기")}
              </button>
              {chatError && <div className="error">{chatError}</div>}
            </div>
            <div className="content">
              <div className="chat">
                {chatLimitReached && (
                  <div className="notice-card">
                    <div className="notice-title">
                      {chatLimitReason === "daily"
                        ? t("Daily limit reached", "오늘 제한 종료")
                        : t("Trial limit reached", "체험 턴이 종료되었습니다")}
                    </div>
                    <div className="meta">
                      {chatLimitReason === "daily"
                        ? t(
                            "You can continue tomorrow or sign in for longer sessions.",
                            "내일 다시 이용하거나 로그인하면 더 길게 사용할 수 있습니다."
                          )
                        : t(
                            "Sign in to continue and manage storage settings.",
                            "로그인 후 계속 대화하고 저장 설정을 선택할 수 있습니다."
                          )}
                    </div>
                    <button className="primary" onClick={() => setActiveTab("Account")}>
                      {t("Go to sign in", "로그인하러 가기")}
                    </button>
                  </div>
                )}
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
              {!authToken && GOOGLE_OAUTH_ENABLED && (
                <>
                  <button
                    className="primary"
                    onClick={startGoogleOauth}
                    disabled={oauthLoading}
                  >
                    {oauthLoading
                      ? t("Connecting to Google...", "구글 로그인 연결 중...")
                      : t("Continue with Google", "Google로 계속하기")}
                  </button>
                  {oauthError && <div className="error">{oauthError}</div>}
                </>
              )}
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
              <div className="settings-card">
                <div className="settings-title">{t("Chat storage", "대화 저장")}</div>
                {!authToken && (
                  <div className="meta">
                    {t(
                      "Sign in to change storage settings.",
                      "저장 설정은 로그인 후 변경할 수 있습니다."
                    )}
                  </div>
                )}
                {authToken && (
                  <>
                    <label className="toggle-row">
                      <span>{t("Store chat history", "대화 저장")}</span>
                      <input
                        type="checkbox"
                        checked={Boolean(serverStoreMessages)}
                        onChange={(e) => requestStoreSettingChange(e.target.checked)}
                        disabled={settingsLoading}
                      />
                    </label>
                    {settingsError && <div className="error">{settingsError}</div>}
                    {settingsNotice && <div className="meta">{settingsNotice}</div>}
                    {serverStoreMessages !== null && !chatStorageSynced && (
                      <div className="notice-card">
                        <div className="notice-title">
                          {t("Apply your local default?", "로컬 기본값을 반영할까요?")}
                        </div>
                        <div className="meta">
                          {t(
                            `Current local default: ${chatStorageConsent ? "ON" : "OFF"}`,
                            `현재 로컬 기본값: ${chatStorageConsent ? "ON" : "OFF"}`
                          )}
                        </div>
                        <div className="notice-actions">
                          <button className="primary" onClick={syncLocalPreference}>
                            {t("Apply to server", "서버에 반영")}
                          </button>
                          <button className="ghost" onClick={dismissSyncPrompt}>
                            {t("Later", "나중에")}
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
              <div className="settings-card">
                <div className="settings-title">
                  {t("OpenAI citations", "OpenAI 인용")}
                </div>
                {!authToken && (
                  <div className="meta">
                    {t(
                      "Sign in to configure OpenAI citations.",
                      "OpenAI 인용 설정은 로그인 후 변경할 수 있습니다."
                    )}
                  </div>
                )}
                {authToken && (
                  <>
                    <label className="toggle-row">
                      <span>{t("Use OpenAI for citations", "인용 시 OpenAI 사용")}</span>
                      <input
                        type="checkbox"
                        checked={Boolean(openaiEnabled)}
                        onChange={(e) => requestOpenaiToggle(e.target.checked)}
                        disabled={openaiSettingsLoading}
                      />
                    </label>
                    <div className="meta">
                      {openaiKeySet
                        ? t("API key saved.", "API 키가 저장되어 있습니다.")
                        : t("No API key saved.", "저장된 API 키가 없습니다.")}
                    </div>
                    <label>
                      {t("OpenAI API key", "OpenAI API 키")}
                      <input
                        type="password"
                        value={openaiKeyInput}
                        placeholder="sk-..."
                        onChange={(e) => setOpenaiKeyInput(e.target.value)}
                      />
                    </label>
                    <div className="notice-actions">
                      <button
                        className="primary"
                        onClick={saveOpenaiKey}
                        disabled={openaiSettingsLoading || !openaiKeyInput.trim()}
                      >
                        {t("Save key", "키 저장")}
                      </button>
                      <button
                        className="ghost"
                        onClick={clearOpenaiKey}
                        disabled={openaiSettingsLoading || !openaiKeySet}
                      >
                        {t("Clear key", "키 삭제")}
                      </button>
                    </div>
                    {openaiSettingsError && <div className="error">{openaiSettingsError}</div>}
                    {openaiSettingsNotice && (
                      <div className="meta">{openaiSettingsNotice}</div>
                    )}
                  </>
                )}
              </div>
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
