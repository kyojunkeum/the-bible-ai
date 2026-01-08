import React, { useEffect, useMemo, useRef, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View
} from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

const API_BASE = process.env.EXPO_PUBLIC_API_BASE || "http://localhost:9000";
const DEVICE_ID = "mobile";
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
const TABS = [
  { key: "Reader", labelKo: "홈", labelEn: "Home" },
  { key: "Search", labelKo: "검색", labelEn: "Search" },
  { key: "Chat", labelKo: "상담", labelEn: "Chat" },
  { key: "Settings", labelKo: "설정", labelEn: "Settings" }
];
const MAX_CACHE_CHAPTERS = 200;
const STORAGE_KEYS = {
  reader: "bible:last_reader",
  tab: "bible:last_tab",
  authToken: "bible:auth_token",
  authUser: "bible:auth_user",
  authEmail: "bible:auth_email",
  uiLang: "bible:ui_lang"
};

// ✅ 추가: UI 언어 옵션
const UI_LANGUAGE_OPTIONS = [
  { id: "ko", labelKo: "한국어", labelEn: "Korean" },
  { id: "en", labelKo: "영어", labelEn: "English" }
];

const normalizeUiLang = (lang) => {
  if (!lang) return "ko";
  const v = String(lang).toLowerCase();
  if (v.startsWith("en")) return "en";
  if (v.startsWith("ko")) return "ko";
  return "ko";
};


const makeVerseKey = (bookId, chapter, verse) => `${bookId}:${chapter}:${verse}`;

const getBookDisplayName = (book, uiLang) => {
  if (!book) return "";
  const isEnUi = uiLang === "en";

  // 서버가 ko_name을 주고 있으니, 한국어 UI면 우선 ko_name 사용
  if (!isEnUi) {
    return book.ko_name || book.abbr || book.osis_code || "";
  }

  // 영어 UI면 OSIS → 영어명 매핑 우선
  return (
    EN_BOOK_NAME_BY_OSIS[book.osis_code] ||
    book.en_name || // (서버가 향후 제공하면 사용)
    book.ko_name ||
    book.abbr ||
    book.osis_code ||
    ""
  );
};

const getDeviceLocale = () => {
  if (typeof Intl !== "undefined" && Intl.DateTimeFormat) {
    try {
      return Intl.DateTimeFormat().resolvedOptions().locale;
    } catch (_) {
      return "ko-KR";
    }
  }
  return "ko-KR";
};

export default function App() {

  const [activeTab, setActiveTab] = useState("Reader");
  const [versionId, setVersionId] = useState("krv");

  const [uiLang, setUiLang] = useState("ko");
  const [uiLangModalOpen, setUiLangModalOpen] = useState(false);

  const isEnglishVersion = versionId === "eng-web";

  const deviceLocale = useMemo(() => getDeviceLocale(), []);

  const [books, setBooks] = useState([]);
  const [booksError, setBooksError] = useState("");
  const [booksLoading, setBooksLoading] = useState(false);

  const [selectedBookId, setSelectedBookId] = useState(1);
  const [chapter, setChapter] = useState("1");
  const [chapterData, setChapterData] = useState(null);
  const [chapterError, setChapterError] = useState("");
  const [chapterNotice, setChapterNotice] = useState("");
  const [chapterLoading, setChapterLoading] = useState(false);
  const [bookModalOpen, setBookModalOpen] = useState(false);
  const [versionModalOpen, setVersionModalOpen] = useState(false);
  const [chapterModalOpen, setChapterModalOpen] = useState(false);

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

  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authCaptcha, setAuthCaptcha] = useState("");
  const [authUserId, setAuthUserId] = useState("");
  const [authToken, setAuthToken] = useState("");
  const [authError, setAuthError] = useState("");
  const [authNotice, setAuthNotice] = useState("");
  const [authLoading, setAuthLoading] = useState(false);

  const [bookmarks, setBookmarks] = useState([]);
  const [bookmarksLoading, setBookmarksLoading] = useState(false);
  const [bookmarksError, setBookmarksError] = useState("");
  const [memos, setMemos] = useState([]);
  const [memosLoading, setMemosLoading] = useState(false);
  const [memosError, setMemosError] = useState("");
  const [memoModalOpen, setMemoModalOpen] = useState(false);
  const [memoDraft, setMemoDraft] = useState("");
  const [memoTarget, setMemoTarget] = useState(null);
  const [memoSaving, setMemoSaving] = useState(false);
  const [bookmarkSavingKey, setBookmarkSavingKey] = useState("");
  const [activeVerseKey, setActiveVerseKey] = useState("");

  const [restoreDone, setRestoreDone] = useState(false);
  const [initialLoadDone, setInitialLoadDone] = useState(false);

  const chapterCache = useRef(new Map());
  const cacheOrder = useRef([]);

  const isEnglishUI = uiLang === "en";
  const t = (en, ko) => (isEnglishUI ? en : ko);

  const versionOptions = useMemo(
    () =>
      VERSION_OPTIONS.map((item) => ({
        ...item,
        label: isEnglishUI ? item.labelEn : item.labelKo
      })),
    [isEnglishUI]
  );
  const tabOptions = useMemo(
    () =>
      TABS.map((tab) => ({
        ...tab,
        label: isEnglishUI ? tab.labelEn : tab.labelKo
      })),
    [isEnglishUI]
  );
  const selectedVersion = useMemo(() => {
    return versionOptions.find((item) => item.id === versionId) || {
      id: versionId,
      label: versionId
    };
  }, [versionId, versionOptions]);

  const touchCacheKey = (key) => {
    cacheOrder.current = cacheOrder.current.filter((item) => item !== key);
    cacheOrder.current.push(key);
    while (cacheOrder.current.length > MAX_CACHE_CHAPTERS) {
      const evicted = cacheOrder.current.shift();
      if (evicted) chapterCache.current.delete(evicted);
    }
  };

  const getCachedChapter = (key) => {
    const cached = chapterCache.current.get(key);
    if (cached) {
      touchCacheKey(key);
    }
    return cached || null;
  };

  const setCachedChapter = (key, payload) => {
    const record = { ...payload, cached_at: new Date().toISOString() };
    chapterCache.current.set(key, record);
    touchCacheKey(key);
  };

  const selectedBook = useMemo(
    () => books.find((book) => book.book_id === Number(selectedBookId)),
    [books, selectedBookId]
  );
  const selectedBookName = useMemo(
    () => getBookDisplayName(selectedBook, uiLang),
    [selectedBook, uiLang]
  );
  const booksById = useMemo(
    () => new Map(books.map((book) => [book.book_id, book])),
    [books]
  );
  const getResultBookName = (item) => {
    const book = booksById.get(item.book_id);
    return getBookDisplayName(book, uiLang) || item.book_name;
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

  const chapterOptions = useMemo(() => {
    const count = Number(selectedBook?.chapter_count || 0);
    if (!count) return [];
    return Array.from({ length: count }, (_, idx) => idx + 1);
  }, [selectedBook?.chapter_count]);

  useEffect(() => {
    let cancelled = false;
    const restoreState = async () => {
      try {
        const readerRaw = await AsyncStorage.getItem(STORAGE_KEYS.reader);
        if (readerRaw) {
          const saved = JSON.parse(readerRaw);
          if (saved?.versionId) setVersionId(saved.versionId);
          if (saved?.bookId) setSelectedBookId(saved.bookId);
          if (saved?.chapter) setChapter(String(saved.chapter));
        }
        const savedTab = await AsyncStorage.getItem(STORAGE_KEYS.tab);
        if (savedTab && TABS.some((tab) => tab.key === savedTab)) {
          setActiveTab(savedTab);
        }
        const token = await AsyncStorage.getItem(STORAGE_KEYS.authToken);
        if (token) setAuthToken(token);
        const userId = await AsyncStorage.getItem(STORAGE_KEYS.authUser);
        if (userId) setAuthUserId(userId);
        const email = await AsyncStorage.getItem(STORAGE_KEYS.authEmail);
        if (email) setAuthEmail(email);

        // ✅ (D 추가) UI 언어 복원
        const savedUiLang = await AsyncStorage.getItem(STORAGE_KEYS.uiLang);
        if (savedUiLang) {
          setUiLang(normalizeUiLang(savedUiLang));
        } else {
          // 최초 실행이면 기기 로케일 기반
          setUiLang(normalizeUiLang(savedUiLang ?? deviceLocale));
        }


      } catch (_) {
        // Ignore storage restore failures
      } finally {
        if (!cancelled) setRestoreDone(true);
      }
    };
    restoreState();
    return () => {
      cancelled = true;
    };
  }, [deviceLocale]);

  useEffect(() => {
    AsyncStorage.setItem(STORAGE_KEYS.tab, activeTab).catch(() => {});
  }, [activeTab]);

  useEffect(() => {
  AsyncStorage.setItem(STORAGE_KEYS.uiLang, uiLang).catch(() => {});
}, [uiLang]);

  useEffect(() => {
    if (authToken) {
      AsyncStorage.setItem(STORAGE_KEYS.authToken, authToken).catch(() => {});
    } else {
      AsyncStorage.removeItem(STORAGE_KEYS.authToken).catch(() => {});
    }
    if (authUserId) {
      AsyncStorage.setItem(STORAGE_KEYS.authUser, authUserId).catch(() => {});
    } else {
      AsyncStorage.removeItem(STORAGE_KEYS.authUser).catch(() => {});
    }
    if (authEmail) {
      AsyncStorage.setItem(STORAGE_KEYS.authEmail, authEmail).catch(() => {});
    } else {
      AsyncStorage.removeItem(STORAGE_KEYS.authEmail).catch(() => {});
    }
  }, [authToken, authUserId, authEmail]);

  useEffect(() => {
    let cancelled = false;
    const loadBooks = async () => {
      // ✅ 버전 전환 시 이전 상태 제거(레이스 방지)
      setBooks([]);
      setChapterData(null);
      setChapterError("");
      setChapterNotice("");
      setBooksError("");
      setBooksLoading(true);
      try {
        const res = await fetch(`${API_BASE}/v1/bible/${versionId}/books`);
        if (!res.ok) throw new Error(t("Failed to load books.", "책 목록을 불러오지 못했습니다."));
        const data = await res.json();
        if (!cancelled) {
          const items = data.items || [];
          setBooks(items);
          if (items.length > 0) {
            const numericSelected = Number(selectedBookId);
            const hasSelected = items.some((book) => book.book_id === numericSelected);
            if (!selectedBookId || !hasSelected) {
              setSelectedBookId(items[0].book_id);
            }
          }
        }
      } catch (err) {
        if (!cancelled) setBooksError(String(err.message || err));
      } finally {
        if (!cancelled) setBooksLoading(false);
      }
    };
    loadBooks();
    return () => {
      cancelled = true;
    };
  }, [versionId]);

  // ✅ 버전이 바뀌면 Reader 탭에서 자동으로 본문 로딩
  useEffect(() => {
    if (!restoreDone) return;
    if (!initialLoadDone) return;
    if (activeTab !== "Reader") return;
    if (!books.length) return;
    if (!selectedBookId || !chapter) return;

    // versionId가 바뀐 시점에 현재 선택(book/chapter) 기준으로 새 버전 본문 로드
    loadChapter();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versionId, restoreDone, activeTab, books.length, selectedBookId, chapter]);

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

  useEffect(() => {
    setMemoModalOpen(false);
    setMemoTarget(null);
    setMemoDraft("");
    setActiveVerseKey("");
  }, [versionId, selectedBookId, chapter]);

  useEffect(() => {
    const maxChapter = Number(selectedBook?.chapter_count || 0);
    if (!maxChapter) return;
    const current = Number.parseInt(chapter, 10);
    if (!current || current < 1) {
      setChapter("1");
      return;
    }
    if (current > maxChapter) {
      setChapter(String(maxChapter));
    }
  }, [selectedBook?.chapter_count]);

  useEffect(() => {
    if (!restoreDone || initialLoadDone) return;
    if (!books.length || !selectedBookId || !chapter) return;
    loadChapter();
    setInitialLoadDone(true);
  }, [restoreDone, initialLoadDone, books.length, selectedBookId, chapter, versionId]);

  const persistLastRead = async (payload) => {
    try {
      await AsyncStorage.setItem(STORAGE_KEYS.reader, JSON.stringify(payload));
    } catch (_) {
      // Ignore storage failures
    }
  };

  // ✅ 버전이 바뀌면 채팅 세션/대화 초기화 (새 세션 유도)
  useEffect(() => {
    setConversationId("");
    setChatMessages([]);
    setChatError("");
    setChatInput("");
  }, [versionId]);

  const loadChapter = async (override) => {
    setChapterError("");
    setChapterNotice("");
    setChapterLoading(true);
    const targetBookId =
      override?.bookId !== undefined ? Number(override.bookId) : Number(selectedBookId);
    const targetBook =
      books.find((book) => book.book_id === targetBookId) || selectedBook;
    const maxChapter = Number(targetBook?.chapter_count || 0);
    const targetChapterInput =
      override?.chapter !== undefined ? String(override.chapter) : chapter;
    const normalizedChapter = Math.max(1, Number.parseInt(targetChapterInput, 10) || 1);
    const boundedChapter = maxChapter
      ? Math.min(normalizedChapter, maxChapter)
      : normalizedChapter;
    if (override?.bookId !== undefined) {
      setSelectedBookId(targetBookId);
    }
    if (String(boundedChapter) !== targetChapterInput) {
      setChapter(String(boundedChapter));
    }
    if (override?.chapter !== undefined && String(boundedChapter) === targetChapterInput) {
      setChapter(String(boundedChapter));
    }
    const cacheKey = `${versionId}:${targetBookId}:${boundedChapter}`;
    const cached = getCachedChapter(cacheKey);
    // ✅ 캐시가 있으면 즉시 렌더링 (빠른 표시)
    if (cached?.verses?.length) {
      setChapterData(cached);
      setChapterError(""); // 오프라인 문구가 남아있지 않게
      setChapterNotice(t("Showing cached content; checking for updates...", "캐시로 먼저 표시하고 최신 본문을 확인 중입니다."));
    }
    try {
      const res = await fetch(
        `${API_BASE}/v1/bible/${versionId}/books/${targetBookId}/chapters/${boundedChapter}`
      );
      if (!res.ok) throw new Error(t("Failed to load chapter.", "장 본문을 불러오지 못했습니다."));
      const data = await res.json();
      if (cached?.content_hash && cached.content_hash !== data.content_hash) {
        setChapterNotice(
          t("Content updated; cache refreshed.", "본문이 업데이트되어 캐시를 갱신했습니다.")
        );
      } else if (cached) {
      // 캐시가 있었는데 동일하면 "확인 완료" 정도로 정리 가능(원하면 제거해도 됨)
      setChapterNotice("");
      }
      setCachedChapter(cacheKey, data);
      setChapterData(data);
      await persistLastRead({
        versionId,
        bookId: targetBookId,
        chapter: boundedChapter
      });
    } catch (err) {
      if (cached) {
        setChapterData(cached);
        setChapterError(t("Showing offline cache.", "오프라인 캐시로 표시 중입니다."));
        await persistLastRead({
          versionId,
          bookId: targetBookId,
          chapter: boundedChapter
        });
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
      body: JSON.stringify({ device_id: DEVICE_ID, locale: deviceLocale, version_id: versionId })
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
        body: JSON.stringify({ user_message: userMessage, client_context: { app_version: "mobile" } })
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
    const key = makeVerseKey(bookId, Number(chapter), verse);
    const isBookmarked = bookmarksByKey.has(key);
    setBookmarksError("");
    setBookmarkSavingKey(key);
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
    } finally {
      setBookmarkSavingKey("");
    }
  };

  const openMemoEditor = (bookId, verse) => {
    if (!authToken) {
      setMemosError(t("Sign in to use memos.", "로그인 후 메모를 사용할 수 있습니다."));
      return;
    }
    const key = makeVerseKey(bookId, Number(chapter), verse);
    const memoText = memosByKey.get(key)?.memo_text || "";
    setMemoTarget({ bookId, chapter: Number(chapter), verse });
    setMemoDraft(memoText);
    setMemosError("");
    setMemoModalOpen(true);
  };

  const saveMemo = async () => {
    if (!memoTarget) return;
    if (!authToken) {
      setMemosError(t("Sign in to use memos.", "로그인 후 메모를 사용할 수 있습니다."));
      return;
    }
    const memoText = memoDraft.trim();
    if (!memoText) {
      setMemosError(t("Please enter a memo.", "메모를 입력해주세요."));
      return;
    }
    setMemoSaving(true);
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
          book_id: memoTarget.bookId,
          chapter: memoTarget.chapter,
          verse: memoTarget.verse,
          memo_text: memoText
        })
      });
      if (!res.ok) throw new Error(t("Failed to save memo.", "메모 저장에 실패했습니다."));
      await refreshMemos();
      setMemoModalOpen(false);
      setMemoTarget(null);
      setMemoDraft("");
    } catch (err) {
      setMemosError(String(err.message || err));
    } finally {
      setMemoSaving(false);
    }
  };

  const deleteMemo = async () => {
    if (!memoTarget) return;
    if (!authToken) {
      setMemosError(t("Sign in to use memos.", "로그인 후 메모를 사용할 수 있습니다."));
      return;
    }
    setMemoSaving(true);
    setMemosError("");
    try {
      const params = new URLSearchParams({
        version_id: versionId,
        book_id: String(memoTarget.bookId),
        chapter: String(memoTarget.chapter),
        verse: String(memoTarget.verse)
      });
      const res = await fetch(`${API_BASE}/v1/bible/memos?${params.toString()}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${authToken}` }
      });
      if (!res.ok) throw new Error(t("Failed to delete memo.", "메모 삭제에 실패했습니다."));
      await refreshMemos();
      setMemoModalOpen(false);
      setMemoTarget(null);
      setMemoDraft("");
    } catch (err) {
      setMemosError(String(err.message || err));
    } finally {
      setMemoSaving(false);
    }
  };

  const jumpToBookmark = (item) => {
    setActiveTab("Reader");
    setActiveVerseKey(makeVerseKey(item.book_id, item.chapter, item.verse));
    loadChapter({ bookId: item.book_id, chapter: item.chapter });
  };

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.root} edges={["top", "bottom"]}>
        <KeyboardAvoidingView
          style={styles.layout}
          behavior={Platform.OS === "ios" ? "padding" : "height"}
          keyboardVerticalOffset={Platform.OS === "ios" ? 10 : 0}
        >
          <ScrollView
            style={styles.scroll}
            contentContainerStyle={styles.container}
            keyboardShouldPersistTaps="handled"
          >
            <View style={styles.hero}>
              <Text style={styles.eyebrow}>{t("Peace", "평안")}</Text>
              <Text style={styles.title}>
                {t("Safe scripture, guided through conversation", "말씀을 대화로, 안전하게")}
              </Text>
              <Text style={styles.sub}>
                {t(
                  "Reader · Search · Counseling in one app.",
                  "읽기 · 검색 · 상담을 하나의 앱에서 경험합니다."
                )}
              </Text>
            </View>

            {activeTab === "Reader" && (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>{t("Home", "홈")}</Text>
                {booksError ? <Text style={styles.error}>{booksError}</Text> : null}
                <TouchableOpacity
                  style={styles.bookSelect}
                  onPress={() => setVersionModalOpen(true)}
                >
                  <Text style={styles.bookSelectLabel}>{t("Bible version", "성경 종류")}</Text>
                  <Text style={styles.bookSelectValue}>{selectedVersion.label}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.bookSelect}
                  onPress={() => setBookModalOpen(true)}
                  disabled={booksLoading || books.length === 0}
                >
                  <Text style={styles.bookSelectLabel}>{t("Select book", "책 선택")}</Text>
                  <Text style={styles.bookSelectValue}>
                    {booksLoading
                      ? t("Loading...", "불러오는 중...")
                      : selectedBookName || t("No books available", "책 목록이 없습니다")}
                  </Text>
                </TouchableOpacity>
                <View style={styles.row}>
                  <View style={styles.inputWrap}>
                    <Text style={styles.label}>{t("Chapter", "장")}</Text>
                    <TouchableOpacity
                      style={[
                        styles.selectInput,
                        !selectedBook?.chapter_count && styles.selectInputDisabled
                      ]}
                      onPress={() => setChapterModalOpen(true)}
                      disabled={!selectedBook?.chapter_count}
                    >
                      <Text
                        style={[
                          styles.selectInputText,
                          !selectedBook?.chapter_count && styles.selectInputTextDisabled
                        ]}
                      >
                        {selectedBook?.chapter_count
                          ? isEnglishVersion
                            ? `Chapter ${chapter} / ${selectedBook.chapter_count}`
                            : `${chapter}장 / ${selectedBook.chapter_count}장`
                          : t("Select a book first.", "책을 먼저 선택하세요")}
                      </Text>
                    </TouchableOpacity>
                  </View>
                  <TouchableOpacity style={styles.primary} onPress={loadChapter}>
                    <Text style={styles.primaryText}>
                      {chapterLoading
                        ? t("Loading", "불러오는 중")
                        : t("Read chapter", "장 읽기")}
                    </Text>
                  </TouchableOpacity>
                </View>
                {chapterError ? <Text style={styles.error}>{chapterError}</Text> : null}
                {chapterNotice ? <Text style={styles.meta}>{chapterNotice}</Text> : null}
                <Text style={styles.meta}>
                  {t(
                    "Long-press a verse to reveal bookmark and memo actions.",
                    "구절을 길게 누르면 북마크/메모 메뉴가 나타납니다."
                  )}
                </Text>
                <Text style={styles.meta}>
                  {bookmarksLoading || memosLoading
                    ? t("Loading bookmarks/memos", "북마크/메모 불러오는 중")
                    : t(
                        `Bookmarks ${bookmarks.length} · Memos ${memos.length}`,
                        `북마크 ${bookmarks.length} · 메모 ${memos.length}`
                      )}
                </Text>
                {!authToken ? (
                  <Text style={styles.meta}>
                    {t(
                      "Sign in to use bookmarks and memos.",
                      "로그인 후 북마크/메모를 사용할 수 있습니다."
                    )}
                  </Text>
                ) : null}
                {bookmarksError ? <Text style={styles.error}>{bookmarksError}</Text> : null}
                {memosError ? <Text style={styles.error}>{memosError}</Text> : null}
                {authToken ? (
                  <View style={styles.card}>
                    <Text style={styles.cardTitle}>{t("Bookmarks", "북마크")}</Text>
                    {bookmarks.length === 0 ? (
                      <Text style={styles.empty}>
                        {t("No bookmarks yet.", "북마크가 없습니다.")}
                      </Text>
                    ) : (
                      bookmarks.map((item) => (
                        <Pressable
                          key={`${item.book_id}-${item.chapter}-${item.verse}`}
                          style={styles.bookmarkItem}
                          onPress={() => jumpToBookmark(item)}
                        >
                          <Text style={styles.bookmarkTitle}>
                            {getResultBookName(item)} {item.chapter}:{item.verse}
                          </Text>
                          <Text style={styles.bookmarkHint}>
                            {t("Tap to open", "눌러서 열기")}
                          </Text>
                        </Pressable>
                      ))
                    )}
                  </View>
                ) : null}
                <View style={styles.card}>
                  <Text style={styles.cardTitle}>
                    {selectedBookName
                      ? isEnglishVersion
                        ? `${selectedBookName} ${chapter}`
                        : `${selectedBookName} ${chapter}장`
                      : t("Passage", "본문")}
                  </Text>
                  {chapterData?.verses?.map((verse) => {
                    const verseKey = makeVerseKey(
                      Number(selectedBookId),
                      Number(chapter),
                      verse.verse
                    );
                    const isBookmarked = bookmarksByKey.has(verseKey);
                    const memoText = memosByKey.get(verseKey)?.memo_text;
                    const isActive = activeVerseKey === verseKey;
                    const bookmarkLabel = isEnglishVersion
                      ? isBookmarked
                        ? "Bookmarked"
                        : "Bookmark"
                      : isBookmarked
                        ? "북마크됨"
                        : "북마크";
                    const memoLabel = isEnglishVersion
                      ? memoText
                        ? "Edit memo"
                        : "Memo"
                      : memoText
                        ? "메모 수정"
                        : "메모";
                    const closeLabel = isEnglishVersion ? "Close" : "닫기";
                    return (
                      <View key={verse.verse} style={styles.verseItem}>
                        <Pressable
                          onLongPress={() => setActiveVerseKey(verseKey)}
                          delayLongPress={250}
                        >
                          <Text style={styles.verseLine}>
                            <Text style={styles.verseNum}>{verse.verse} </Text>
                            {verse.text}
                          </Text>
                        </Pressable>
                        {isActive ? (
                          <View style={styles.verseActions}>
                            <TouchableOpacity
                              style={[
                                styles.actionChip,
                                isBookmarked && styles.actionChipActive,
                                !authToken && styles.actionChipDisabled
                              ]}
                              onPress={() => toggleBookmark(Number(selectedBookId), verse.verse)}
                              disabled={!authToken || bookmarkSavingKey === verseKey}
                            >
                              <Text
                              style={[
                                styles.actionChipText,
                                isBookmarked && styles.actionChipTextActive,
                                !authToken && styles.actionChipTextDisabled
                              ]}
                            >
                              {bookmarkLabel}
                            </Text>
                          </TouchableOpacity>
                          <TouchableOpacity
                            style={[
                              styles.actionChip,
                              memoText && styles.actionChipActive,
                                !authToken && styles.actionChipDisabled
                              ]}
                              onPress={() => openMemoEditor(Number(selectedBookId), verse.verse)}
                              disabled={!authToken}
                            >
                              <Text
                              style={[
                                styles.actionChipText,
                                memoText && styles.actionChipTextActive,
                                !authToken && styles.actionChipTextDisabled
                              ]}
                            >
                              {memoLabel}
                            </Text>
                          </TouchableOpacity>
                          <TouchableOpacity
                              style={styles.actionChip}
                              onPress={() => setActiveVerseKey("")}
                            >
                              <Text style={styles.actionChipText}>{closeLabel}</Text>
                            </TouchableOpacity>
                          </View>
                        ) : null}
                        {isActive && memoText ? (
                          <Text style={styles.memoText}>
                            {t("Memo:", "메모:")} {memoText}
                          </Text>
                        ) : null}
                      </View>
                    );
                  })}
                  {!chapterData && (
                    <Text style={styles.empty}>
                      {t("Loading passage...", "본문을 불러오는 중입니다.")}
                    </Text>
                  )}
                </View>
              </View>
            )}

            {activeTab === "Search" && (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>{t("Search", "검색")}</Text>
                <TextInput
                  style={styles.input}
                  placeholder={t("Genesis, peace, anxiety", "태초, 평안, 불안")}
                  value={searchQuery}
                  onChangeText={setSearchQuery}
                />
                <TouchableOpacity style={styles.primary} onPress={handleSearch}>
                  <Text style={styles.primaryText}>
                    {searchLoading ? t("Searching", "검색 중") : t("Search", "검색")}
                  </Text>
                </TouchableOpacity>
                {searchError ? <Text style={styles.error}>{searchError}</Text> : null}
                <Text style={styles.meta}>
                  {t(`Total ${searchTotal}`, `총 ${searchTotal}건`)}
                </Text>
                <View style={styles.card}>
                  {searchResults.length === 0 ? (
                    <Text style={styles.empty}>{t("No results found.", "결과가 없습니다.")}</Text>
                  ) : (
                    searchResults.map((item, idx) => (
                      <View key={`${item.book_id}-${idx}`} style={styles.resultItem}>
                        <Text style={styles.resultTitle}>
                          {getResultBookName(item)} {item.chapter}:{item.verse}
                        </Text>
                        <Text style={styles.resultSnippet}>{item.snippet || item.text}</Text>
                      </View>
                    ))
                  )}
                </View>
              </View>
            )}

            {activeTab === "Chat" && (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>{t("Counseling", "상담")}</Text>
                {chatError ? <Text style={styles.error}>{chatError}</Text> : null}
                <View style={styles.chatPanel}>
                  <View style={styles.chatList}>
                    {chatMessages.length === 0 && !chatLoading ? (
                      <Text style={styles.empty}>
                        {t("Start a conversation.", "대화를 시작해 주세요.")}
                      </Text>
                    ) : (
                      chatMessages.map((msg, idx) => (
                        <View
                          key={`${msg.role}-${idx}`}
                          style={[
                            styles.chatRow,
                            msg.role === "user" ? styles.chatRowUser : styles.chatRowAssistant
                          ]}
                        >
                          {msg.role !== "user" ? (
                            <View style={styles.avatar}>
                              <Text style={styles.avatarText}>{t("Peace", "평안")}</Text>
                            </View>
                          ) : null}
                          <View
                            style={[
                              styles.chatBubble,
                              msg.role === "user"
                                ? styles.chatBubbleUser
                                : styles.chatBubbleAssistant
                            ]}
                          >
                            <Text style={styles.chatText}>{msg.content}</Text>
                          </View>
                          {msg.role === "user" ? (
                            <View style={styles.avatarUser}>
                              <Text style={styles.avatarText}>{t("Me", "나")}</Text>
                            </View>
                          ) : null}
                        </View>
                      ))
                    )}
                    {chatLoading ? (
                      <View style={[styles.chatRow, styles.chatRowAssistant]}>
                        <View style={styles.avatar}>
                          <Text style={styles.avatarText}>{t("Peace", "평안")}</Text>
                        </View>
                        <View style={[styles.chatBubble, styles.chatBubbleAssistant]}>
                          <Text style={styles.chatTextMuted}>
                            {t("Generating response...", "응답 생성 중...")}
                          </Text>
                        </View>
                      </View>
                    ) : null}
                  </View>
                  <View style={styles.chatComposer}>
                    <TextInput
                      style={styles.chatInput}
                      placeholder={t(
                        "I'm anxious and can't sleep lately.",
                        "요즘 불안해서 잠이 안 와요"
                      )}
                      value={chatInput}
                      onChangeText={setChatInput}
                      multiline
                    />
                    <TouchableOpacity
                      style={[styles.chatSend, chatLoading && styles.chatSendDisabled]}
                      onPress={sendMessage}
                      disabled={chatLoading}
                    >
                      <Text style={styles.chatSendText}>{t("Send", "보내기")}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              </View>
            )}

            {activeTab === "Settings" && (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>{t("Settings", "설정")}</Text>
                <View style={styles.card}>
                  <Text style={styles.label}>{t("UI language", "표시 언어")}</Text>

                  <TouchableOpacity
                    style={styles.bookSelect}
                    onPress={() => setUiLangModalOpen(true)}
                  >
                    <Text style={styles.bookSelectLabel}>{t("Select language", "언어 선택")}</Text>
                    <Text style={styles.bookSelectValue}>
                      {uiLang === "en" ? "English" : "한국어"}
                    </Text>
                  </TouchableOpacity>
                </View>

                <View style={styles.card}>
                  <Text style={styles.label}>{t("API address", "API 주소")}</Text>
                  <Text style={styles.settingValue}>{API_BASE}</Text>
                  {conversationId ? (
                    <Text style={styles.meta}>Session: {conversationId}</Text>
                  ) : null}
                </View>

                <View style={styles.card}>
                  <Text style={styles.label}>{t("Account", "계정")}</Text>
                  {authToken ? (
                    <View style={styles.accountInfo}>
                      <Text style={styles.settingValue}>User: {authUserId}</Text>
                      <Text style={styles.meta}>Email: {authEmail}</Text>
                      <TouchableOpacity
                        style={[styles.secondary, authLoading && styles.primaryDisabled]}
                        onPress={handleLogout}
                        disabled={authLoading}
                      >
                        <Text style={styles.secondaryText}>{t("Sign out", "로그아웃")}</Text>
                      </TouchableOpacity>
                    </View>
                  ) : (

                    <View style={styles.accountForm}>
                      <TextInput
                        style={styles.input}
                        placeholder="you@example.com"
                        value={authEmail}
                        onChangeText={setAuthEmail}
                        autoCapitalize="none"
                        keyboardType="email-address"
                      />
                      <TextInput
                        style={styles.input}
                        placeholder={t(
                          "At least 12 characters (max 128)",
                          "12자 이상 (최대 128자)"
                        )}
                        value={authPassword}
                        onChangeText={setAuthPassword}
                        secureTextEntry
                      />
                      <TextInput
                        style={styles.input}
                        placeholder={t(
                          "Captcha token (if required)",
                          "추가 인증 토큰 (필요 시)"
                        )}
                        value={authCaptcha}
                        onChangeText={setAuthCaptcha}
                        autoCapitalize="none"
                      />
                      <TouchableOpacity
                        style={[styles.primary, authLoading && styles.primaryDisabled]}
                        onPress={handleLogin}
                        disabled={authLoading || !authEmail || !authPassword}
                      >
                        <Text style={styles.primaryText}>
                          {authLoading ? t("Working", "처리 중") : t("Sign in", "로그인")}
                        </Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        style={[styles.secondary, authLoading && styles.primaryDisabled]}
                        onPress={handleRegister}
                        disabled={authLoading || !authEmail || !authPassword}
                      >
                        <Text style={styles.secondaryText}>
                          {t("Create account", "회원가입")}
                        </Text>
                      </TouchableOpacity>
                    </View>
                  )}
                  {authError ? <Text style={styles.error}>{authError}</Text> : null}
                  {authNotice ? <Text style={styles.meta}>{authNotice}</Text> : null}
                </View>
              </View>
            )}
            <Modal
              visible={uiLangModalOpen}
              animationType="slide"
              transparent
              onRequestClose={() => setUiLangModalOpen(false)}
            >
              <View style={styles.modalBackdrop}>
                <View style={styles.modalCard}>
                  <Text style={styles.modalTitle}>{t("UI language", "표시 언어")}</Text>

                  <ScrollView style={styles.modalList}>
                    {UI_LANGUAGE_OPTIONS.map((opt) => (
                      <TouchableOpacity
                        key={opt.id}
                        style={[
                          styles.bookOption,
                          uiLang === opt.id && styles.bookOptionActive
                        ]}
                        onPress={() => {
                          setUiLang(opt.id);          // ✅ 언어 변경
                          setUiLangModalOpen(false);  // ✅ 모달 닫기
                        }}
                      >
                        <Text
                          style={[
                            styles.bookOptionText,
                            uiLang === opt.id && styles.bookOptionTextActive
                          ]}
                        >
                          {isEnglishUI ? opt.labelEn : opt.labelKo}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </ScrollView>

                  <TouchableOpacity
                    style={styles.modalClose}
                    onPress={() => setUiLangModalOpen(false)}
                  >
                    <Text style={styles.modalCloseText}>{t("Close", "닫기")}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </Modal>
            <Modal
              visible={bookModalOpen}
              animationType="slide"
              transparent
              onRequestClose={() => setBookModalOpen(false)}
            >
              <View style={styles.modalBackdrop}>
                <View style={styles.modalCard}>
                  <Text style={styles.modalTitle}>{t("Select book", "책 선택")}</Text>
                  <ScrollView style={styles.modalList}>
                    {books.map((book) => (
                      <TouchableOpacity
                        key={book.book_id}
                        style={[
                          styles.bookOption,
                          selectedBookId === book.book_id && styles.bookOptionActive
                        ]}
                        onPress={() => {
                          setSelectedBookId(book.book_id);
                          setBookModalOpen(false);
                        }}
                      >
                        <Text
                          style={[
                            styles.bookOptionText,
                            selectedBookId === book.book_id && styles.bookOptionTextActive
                          ]}
                        >
                          {getBookDisplayName(book, uiLang)} ({isEnglishVersion ? book.osis_code : book.abbr})
                        </Text>
                      </TouchableOpacity>
                    ))}
                    {books.length === 0 && !booksLoading ? (
                      <Text style={styles.empty}>
                        {t("Failed to load books.", "책 목록을 불러오지 못했습니다.")}
                      </Text>
                    ) : null}
                  </ScrollView>
                  <TouchableOpacity
                    style={styles.modalClose}
                    onPress={() => setBookModalOpen(false)}
                  >
                    <Text style={styles.modalCloseText}>{t("Close", "닫기")}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </Modal>
            <Modal
              visible={versionModalOpen}
              animationType="slide"
              transparent
              onRequestClose={() => setVersionModalOpen(false)}
            >
              <View style={styles.modalBackdrop}>
                <View style={styles.modalCard}>
                  <Text style={styles.modalTitle}>{t("Bible version", "성경 종류")}</Text>
                  <ScrollView style={styles.modalList}>
                    {versionOptions.map((version) => (
                      <TouchableOpacity
                        key={version.id}
                        style={[
                          styles.bookOption,
                          versionId === version.id && styles.bookOptionActive
                        ]}
                        onPress={() => {
                          setVersionId(version.id);
                          setVersionModalOpen(false);
                        }}
                      >
                        <Text
                          style={[
                            styles.bookOptionText,
                            versionId === version.id && styles.bookOptionTextActive
                          ]}
                        >
                          {version.label}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </ScrollView>
                  <TouchableOpacity
                    style={styles.modalClose}
                    onPress={() => setVersionModalOpen(false)}
                  >
                    <Text style={styles.modalCloseText}>{t("Close", "닫기")}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </Modal>
            <Modal
              visible={chapterModalOpen}
              animationType="slide"
              transparent
              onRequestClose={() => setChapterModalOpen(false)}
            >
              <View style={styles.modalBackdrop}>
                <View style={styles.modalCard}>
                  <Text style={styles.modalTitle}>
                    {selectedBookName
                      ? isEnglishVersion
                        ? `${selectedBookName} - Select chapter`
                        : `${selectedBookName} 장 선택`
                      : t("Select chapter", "장 선택")}
                  </Text>
                  <ScrollView style={styles.modalList}>
                    <View style={styles.chapterGrid}>
                      {chapterOptions.map((num) => (
                        <TouchableOpacity
                          key={num}
                          style={[
                            styles.chapterChip,
                            Number(chapter) === num && styles.chapterChipActive
                          ]}
                          onPress={() => {
                            setChapter(String(num));
                            setChapterModalOpen(false);
                          }}
                        >
                          <Text
                            style={[
                              styles.chapterChipText,
                              Number(chapter) === num && styles.chapterChipTextActive
                            ]}
                          >
                            {isEnglishVersion ? `Chapter ${num}` : `${num}장`}
                          </Text>
                        </TouchableOpacity>
                      ))}
                      {!chapterOptions.length && (
                        <Text style={styles.empty}>
                          {t("Unable to load chapters.", "장 목록을 불러오지 못했습니다.")}
                        </Text>
                      )}
                    </View>
                  </ScrollView>
                  <TouchableOpacity
                    style={styles.modalClose}
                    onPress={() => setChapterModalOpen(false)}
                  >
                    <Text style={styles.modalCloseText}>{t("Close", "닫기")}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </Modal>
            <Modal
              visible={memoModalOpen}
              animationType="slide"
              transparent
              onRequestClose={() => setMemoModalOpen(false)}
            >
              <KeyboardAvoidingView
                style={styles.modalBackdrop}
                behavior={Platform.OS === "ios" ? "padding" : "height"}
                keyboardVerticalOffset={Platform.OS === "ios" ? 24 : 0}
              >
                <View style={styles.modalCard}>
                  <Text style={styles.modalTitle}>{t("Memo", "메모")}</Text>
                  <TextInput
                    style={[styles.input, styles.memoInput]}
                    placeholder={t("Leave a note for this verse.", "이 절에 대한 메모를 남겨보세요.")}
                    value={memoDraft}
                    onChangeText={setMemoDraft}
                    multiline
                  />
                  {memosError ? <Text style={styles.error}>{memosError}</Text> : null}
                  <View style={styles.modalActions}>
                    <TouchableOpacity
                      style={[styles.primary, memoSaving && styles.primaryDisabled]}
                      onPress={saveMemo}
                      disabled={memoSaving}
                    >
                      <Text style={styles.primaryText}>
                        {memoSaving ? t("Saving", "저장 중") : t("Save", "저장")}
                      </Text>
                    </TouchableOpacity>
                    {memoTarget &&
                    memosByKey.has(
                      makeVerseKey(memoTarget.bookId, memoTarget.chapter, memoTarget.verse)
                    ) ? (
                      <TouchableOpacity
                        style={styles.secondary}
                        onPress={deleteMemo}
                        disabled={memoSaving}
                      >
                        <Text style={styles.secondaryText}>{t("Delete", "삭제")}</Text>
                      </TouchableOpacity>
                    ) : null}
                    <TouchableOpacity
                      style={styles.modalClose}
                      onPress={() => setMemoModalOpen(false)}
                      disabled={memoSaving}
                    >
                      <Text style={styles.modalCloseText}>{t("Close", "닫기")}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              </KeyboardAvoidingView>
            </Modal>
          </ScrollView>
          <View style={styles.tabsBar}>
            <View style={styles.tabs}>
              {tabOptions.map((tab) => (
                <TouchableOpacity
                  key={tab.key}
                  style={[styles.tab, activeTab === tab.key && styles.tabActive]}
                  onPress={() => setActiveTab(tab.key)}
                >
                  <Text style={[styles.tabText, activeTab === tab.key && styles.tabTextActive]}>
                    {tab.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: "#f6f1e9"
  },
  layout: {
    flex: 1
  },
  scroll: {
    flex: 1
  },
  container: {
    padding: 20,
    paddingBottom: 24,
    gap: 16
  },
  hero: {
    backgroundColor: "#fff",
    borderRadius: 24,
    padding: 20,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    elevation: 3
  },
  eyebrow: {
    letterSpacing: 2,
    textTransform: "uppercase",
    fontSize: 12,
    color: "#2f6b5b"
  },
  title: {
    fontSize: 26,
    fontWeight: "700",
    marginVertical: 8,
    color: "#1d1b1a"
  },
  sub: {
    fontSize: 14,
    color: "#5d5854"
  },
  badge: {
    marginTop: 12,
    backgroundColor: "#f7efe6",
    borderRadius: 16,
    padding: 12
  },
  badgeLabel: {
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: 1,
    color: "#5d5854"
  },
  badgeValue: {
    marginTop: 4,
    fontSize: 14,
    fontWeight: "600"
  },
  badgeMeta: {
    marginTop: 6,
    fontSize: 12,
    color: "#5d5854"
  },
  settingValue: {
    marginTop: 6,
    fontSize: 14,
    fontWeight: "600",
    color: "#1d1b1a"
  },
  tabs: {
    flexDirection: "row",
    gap: 8
  },
  tabsBar: {
    paddingHorizontal: 20,
    paddingTop: 10,
    paddingBottom: 14,
    borderTopWidth: 1,
    borderColor: "#e7ddcf",
    backgroundColor: "#f6f1e9"
  },
  tab: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#e7ddcf",
    alignItems: "center"
  },
  tabActive: {
    backgroundColor: "#1d1b1a",
    borderColor: "#1d1b1a"
  },
  tabText: {
    fontSize: 13,
    color: "#1d1b1a"
  },
  tabTextActive: {
    color: "#fff"
  },
  section: {
    gap: 12
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: "700"
  },
  bookRow: {
    flexGrow: 0
  },
  bookSelect: {
    backgroundColor: "#fff",
    borderRadius: 16,
    padding: 12,
    borderWidth: 1,
    borderColor: "#e7ddcf"
  },
  bookSelectLabel: {
    fontSize: 12,
    color: "#5d5854",
    marginBottom: 4
  },
  bookSelectValue: {
    fontSize: 16,
    fontWeight: "600",
    color: "#1d1b1a"
  },
  bookChip: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#e7ddcf",
    marginRight: 8
  },
  bookChipActive: {
    backgroundColor: "#2f6b5b",
    borderColor: "#2f6b5b"
  },
  bookChipText: {
    color: "#2f6b5b",
    fontWeight: "600"
  },
  bookChipTextActive: {
    color: "#fff"
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12
  },
  inputWrap: {
    flex: 1
  },
  label: {
    fontSize: 12,
    color: "#5d5854",
    marginBottom: 4
  },
  input: {
    backgroundColor: "#fff",
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: "#e7ddcf",
    fontSize: 14
  },
  selectInput: {
    backgroundColor: "#fff",
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: "#e7ddcf",
    minHeight: 42,
    justifyContent: "center"
  },
  selectInputDisabled: {
    backgroundColor: "#f3eee6"
  },
  selectInputText: {
    fontSize: 14,
    color: "#1d1b1a",
    fontWeight: "600"
  },
  selectInputTextDisabled: {
    color: "#9c8f84",
    fontWeight: "400"
  },
  textarea: {
    minHeight: 90,
    textAlignVertical: "top"
  },
  primary: {
    backgroundColor: "#d84c2f",
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 12
  },
  primaryText: {
    color: "#fff",
    fontWeight: "600",
    textAlign: "center"
  },
  card: {
    backgroundColor: "#fff",
    borderRadius: 18,
    padding: 16,
    borderWidth: 1,
    borderColor: "#e7ddcf"
  },
  chatPanel: {
    backgroundColor: "#fff",
    borderRadius: 18,
    padding: 14,
    borderWidth: 1,
    borderColor: "#e7ddcf",
    gap: 12
  },
  chatList: {
    gap: 12
  },
  chatRow: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 8
  },
  chatRowAssistant: {
    justifyContent: "flex-start"
  },
  chatRowUser: {
    justifyContent: "flex-end"
  },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: "#1d1b1a",
    alignItems: "center",
    justifyContent: "center"
  },
  avatarUser: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: "#2f6b5b",
    alignItems: "center",
    justifyContent: "center"
  },
  avatarText: {
    color: "#fff",
    fontSize: 12,
    fontWeight: "700"
  },
  chatBubble: {
    maxWidth: "78%",
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 14
  },
  chatBubbleAssistant: {
    backgroundColor: "#f7efe6"
  },
  chatBubbleUser: {
    backgroundColor: "#e8f3ef"
  },
  chatText: {
    lineHeight: 20,
    color: "#1d1b1a"
  },
  chatTextMuted: {
    lineHeight: 20,
    color: "#5d5854"
  },
  chatComposer: {
    borderTopWidth: 1,
    borderTopColor: "#efe5d6",
    paddingTop: 12,
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 10
  },
  chatInput: {
    flex: 1,
    minHeight: 44,
    maxHeight: 140,
    backgroundColor: "#fff",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#e7ddcf",
    paddingHorizontal: 12,
    paddingVertical: 10
  },
  chatSend: {
    backgroundColor: "#1d1b1a",
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 14
  },
  chatSendDisabled: {
    opacity: 0.5
  },
  chatSendText: {
    color: "#fff",
    fontWeight: "600"
  },
  cardTitle: {
    fontWeight: "700",
    marginBottom: 8
  },
  verseLine: {
    marginBottom: 8,
    lineHeight: 20
  },
  verseNum: {
    color: "#d84c2f",
    fontWeight: "700"
  },
  verseItem: {
    marginBottom: 12
  },
  verseActions: {
    flexDirection: "row",
    gap: 8,
    flexWrap: "wrap",
    marginBottom: 6
  },
  actionChip: {
    borderWidth: 1,
    borderColor: "#e7ddcf",
    borderRadius: 999,
    paddingVertical: 6,
    paddingHorizontal: 12
  },
  actionChipActive: {
    backgroundColor: "#2f6b5b",
    borderColor: "#2f6b5b"
  },
  actionChipDisabled: {
    opacity: 0.5
  },
  actionChipText: {
    fontSize: 12,
    color: "#5d5854",
    fontWeight: "600"
  },
  actionChipTextActive: {
    color: "#fff"
  },
  actionChipTextDisabled: {
    color: "#9c8f84"
  },
  memoText: {
    backgroundColor: "#f7efe6",
    padding: 10,
    borderRadius: 12,
    fontSize: 12,
    color: "#5d5854"
  },
  bookmarkItem: {
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: "#efe5d6"
  },
  bookmarkTitle: {
    fontWeight: "600",
    color: "#1d1b1a"
  },
  bookmarkHint: {
    marginTop: 4,
    fontSize: 12,
    color: "#5d5854"
  },
  resultItem: {
    marginBottom: 12
  },
  resultTitle: {
    fontWeight: "700"
  },
  resultSnippet: {
    marginTop: 4,
    color: "#5d5854"
  },
  empty: {
    textAlign: "center",
    color: "#5d5854"
  },
  meta: {
    color: "#5d5854",
    fontSize: 12
  },
  error: {
    backgroundColor: "#ffe7e0",
    color: "#9a2f1f",
    padding: 10,
    borderRadius: 10
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: "flex-end"
  },
  modalCard: {
    backgroundColor: "#fff",
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 16,
    maxHeight: "70%"
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: "700",
    marginBottom: 12
  },
  modalList: {
    marginBottom: 12
  },
  chapterGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8
  },
  chapterChip: {
    borderWidth: 1,
    borderColor: "#e7ddcf",
    borderRadius: 999,
    paddingVertical: 6,
    paddingHorizontal: 12,
    backgroundColor: "#fff"
  },
  chapterChipActive: {
    backgroundColor: "#2f6b5b",
    borderColor: "#2f6b5b"
  },
  chapterChipText: {
    color: "#1d1b1a",
    fontWeight: "600"
  },
  chapterChipTextActive: {
    color: "#fff"
  },
  bookOption: {
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: "#f0e7dc"
  },
  bookOptionActive: {
    backgroundColor: "#f7efe6"
  },
  bookOptionText: {
    fontSize: 15,
    color: "#1d1b1a"
  },
  bookOptionTextActive: {
    fontWeight: "700",
    color: "#2f6b5b"
  },
  modalClose: {
    backgroundColor: "#1d1b1a",
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: "center"
  },
  modalCloseText: {
    color: "#fff",
    fontWeight: "600"
  },
  modalActions: {
    gap: 10,
    marginTop: 12
  },
  accountInfo: {
    gap: 8,
    marginTop: 8
  },
  accountForm: {
    gap: 10,
    marginTop: 8
  },
  primaryDisabled: {
    opacity: 0.6
  },
  secondary: {
    backgroundColor: "#f7efe6",
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: "center"
  },
  secondaryText: {
    color: "#1d1b1a",
    fontWeight: "600"
  },
  memoInput: {
    minHeight: 100,
    textAlignVertical: "top"
  }
});
