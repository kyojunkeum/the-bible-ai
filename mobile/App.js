import React, { useEffect, useMemo, useRef, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View
} from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

const API_BASE = process.env.EXPO_PUBLIC_API_BASE || "http://localhost:9000";
const VERSION_OPTIONS = [{ id: "krv", label: "개역한글판" }];
const TABS = [
  { key: "Reader", label: "홈" },
  { key: "Search", label: "검색" },
  { key: "Chat", label: "상담" },
  { key: "Settings", label: "설정" }
];
const MAX_CACHE_CHAPTERS = 200;
const STORAGE_KEYS = {
  reader: "bible:last_reader",
  tab: "bible:last_tab"
};

export default function App() {
  const [activeTab, setActiveTab] = useState("Reader");
  const [versionId, setVersionId] = useState("krv");
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

  const [restoreDone, setRestoreDone] = useState(false);
  const [initialLoadDone, setInitialLoadDone] = useState(false);

  const chapterCache = useRef(new Map());
  const cacheOrder = useRef([]);

  const selectedVersion = useMemo(() => {
    return VERSION_OPTIONS.find((item) => item.id === versionId) || {
      id: versionId,
      label: versionId
    };
  }, [versionId]);

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
  }, []);

  useEffect(() => {
    AsyncStorage.setItem(STORAGE_KEYS.tab, activeTab).catch(() => {});
  }, [activeTab]);

  useEffect(() => {
    let cancelled = false;
    const loadBooks = async () => {
      setBooksError("");
      setBooksLoading(true);
      try {
        const res = await fetch(`${API_BASE}/v1/bible/${versionId}/books`);
        if (!res.ok) throw new Error("책 목록을 불러오지 못했습니다.");
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

  const loadChapter = async () => {
    setChapterError("");
    setChapterNotice("");
    setChapterLoading(true);
    const maxChapter = Number(selectedBook?.chapter_count || 0);
    const normalizedChapter = Math.max(1, Number.parseInt(chapter, 10) || 1);
    const boundedChapter = maxChapter
      ? Math.min(normalizedChapter, maxChapter)
      : normalizedChapter;
    if (String(normalizedChapter) !== chapter) {
      setChapter(String(boundedChapter));
    }
    const cacheKey = `${versionId}:${selectedBookId}:${boundedChapter}`;
    const cached = getCachedChapter(cacheKey);
    try {
      const res = await fetch(
        `${API_BASE}/v1/bible/${versionId}/books/${selectedBookId}/chapters/${boundedChapter}`
      );
      if (!res.ok) throw new Error("장 본문을 불러오지 못했습니다.");
      const data = await res.json();
      if (cached?.content_hash && cached.content_hash !== data.content_hash) {
        setChapterNotice("본문이 업데이트되어 캐시를 갱신했습니다.");
      }
      setCachedChapter(cacheKey, data);
      setChapterData(data);
      await persistLastRead({
        versionId,
        bookId: Number(selectedBookId),
        chapter: boundedChapter
      });
    } catch (err) {
      if (cached) {
        setChapterData(cached);
        setChapterError("오프라인 캐시로 표시 중입니다.");
        await persistLastRead({
          versionId,
          bookId: Number(selectedBookId),
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
      body: JSON.stringify({ device_id: "mobile", locale: "ko-KR", version_id: versionId })
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
        body: JSON.stringify({ user_message: userMessage, client_context: { app_version: "mobile" } })
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
              <Text style={styles.eyebrow}>평안</Text>
              <Text style={styles.title}>말씀을 대화로, 안전하게</Text>
              <Text style={styles.sub}>읽기 · 검색 · 상담을 하나의 앱에서 경험합니다.</Text>
            </View>

            {activeTab === "Reader" && (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>홈</Text>
                {booksError ? <Text style={styles.error}>{booksError}</Text> : null}
                <TouchableOpacity
                  style={styles.bookSelect}
                  onPress={() => setVersionModalOpen(true)}
                >
                  <Text style={styles.bookSelectLabel}>성경 종류</Text>
                  <Text style={styles.bookSelectValue}>{selectedVersion.label}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.bookSelect}
                  onPress={() => setBookModalOpen(true)}
                  disabled={booksLoading || books.length === 0}
                >
                  <Text style={styles.bookSelectLabel}>책 선택</Text>
                  <Text style={styles.bookSelectValue}>
                    {booksLoading
                      ? "불러오는 중..."
                      : selectedBook?.ko_name || "책 목록이 없습니다"}
                  </Text>
                </TouchableOpacity>
                <View style={styles.row}>
                  <View style={styles.inputWrap}>
                    <Text style={styles.label}>장</Text>
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
                          ? `${chapter}장 / ${selectedBook.chapter_count}장`
                          : "책을 먼저 선택하세요"}
                      </Text>
                    </TouchableOpacity>
                  </View>
                  <TouchableOpacity style={styles.primary} onPress={loadChapter}>
                    <Text style={styles.primaryText}>
                      {chapterLoading ? "불러오는 중" : "장 읽기"}
                    </Text>
                  </TouchableOpacity>
                </View>
                {chapterError ? <Text style={styles.error}>{chapterError}</Text> : null}
                {chapterNotice ? <Text style={styles.meta}>{chapterNotice}</Text> : null}
                <View style={styles.card}>
                  <Text style={styles.cardTitle}>
                    {selectedBook?.ko_name
                      ? `${selectedBook.ko_name} ${chapter}장`
                      : "본문"}
                  </Text>
                  {chapterData?.verses?.map((verse) => (
                    <Text key={verse.verse} style={styles.verseLine}>
                      <Text style={styles.verseNum}>{verse.verse} </Text>
                      {verse.text}
                    </Text>
                  ))}
                  {!chapterData && (
                    <Text style={styles.empty}>본문을 불러오는 중입니다.</Text>
                  )}
                </View>
              </View>
            )}

            {activeTab === "Search" && (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>검색</Text>
                <TextInput
                  style={styles.input}
                  placeholder="태초, 평안, 불안"
                  value={searchQuery}
                  onChangeText={setSearchQuery}
                />
                <TouchableOpacity style={styles.primary} onPress={handleSearch}>
                  <Text style={styles.primaryText}>
                    {searchLoading ? "검색 중" : "검색"}
                  </Text>
                </TouchableOpacity>
                {searchError ? <Text style={styles.error}>{searchError}</Text> : null}
                <Text style={styles.meta}>총 {searchTotal}건</Text>
                <View style={styles.card}>
                  {searchResults.length === 0 ? (
                    <Text style={styles.empty}>결과가 없습니다.</Text>
                  ) : (
                    searchResults.map((item, idx) => (
                      <View key={`${item.book_id}-${idx}`} style={styles.resultItem}>
                        <Text style={styles.resultTitle}>
                          {item.book_name} {item.chapter}:{item.verse}
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
                <Text style={styles.sectionTitle}>상담</Text>
                {chatError ? <Text style={styles.error}>{chatError}</Text> : null}
                <View style={styles.chatPanel}>
                  <View style={styles.chatList}>
                    {chatMessages.length === 0 && !chatLoading ? (
                      <Text style={styles.empty}>대화를 시작해 주세요.</Text>
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
                              <Text style={styles.avatarText}>평안</Text>
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
                              <Text style={styles.avatarText}>나</Text>
                            </View>
                          ) : null}
                        </View>
                      ))
                    )}
                    {chatLoading ? (
                      <View style={[styles.chatRow, styles.chatRowAssistant]}>
                        <View style={styles.avatar}>
                          <Text style={styles.avatarText}>평안</Text>
                        </View>
                        <View style={[styles.chatBubble, styles.chatBubbleAssistant]}>
                          <Text style={styles.chatTextMuted}>응답 생성 중...</Text>
                        </View>
                      </View>
                    ) : null}
                  </View>
                  <View style={styles.chatComposer}>
                    <TextInput
                      style={styles.chatInput}
                      placeholder="요즘 불안해서 잠이 안 와요"
                      value={chatInput}
                      onChangeText={setChatInput}
                      multiline
                    />
                    <TouchableOpacity
                      style={[styles.chatSend, chatLoading && styles.chatSendDisabled]}
                      onPress={sendMessage}
                      disabled={chatLoading}
                    >
                      <Text style={styles.chatSendText}>보내기</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              </View>
            )}

            {activeTab === "Settings" && (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>설정</Text>
                <View style={styles.card}>
                  <Text style={styles.label}>API 주소</Text>
                  <Text style={styles.settingValue}>{API_BASE}</Text>
                  {conversationId ? (
                    <Text style={styles.meta}>Session: {conversationId}</Text>
                  ) : null}
                </View>
              </View>
            )}
            <Modal
              visible={bookModalOpen}
              animationType="slide"
              transparent
              onRequestClose={() => setBookModalOpen(false)}
            >
              <View style={styles.modalBackdrop}>
                <View style={styles.modalCard}>
                  <Text style={styles.modalTitle}>책 선택</Text>
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
                          {book.ko_name} ({book.abbr})
                        </Text>
                      </TouchableOpacity>
                    ))}
                    {books.length === 0 && !booksLoading ? (
                      <Text style={styles.empty}>책 목록을 불러오지 못했습니다.</Text>
                    ) : null}
                  </ScrollView>
                  <TouchableOpacity
                    style={styles.modalClose}
                    onPress={() => setBookModalOpen(false)}
                  >
                    <Text style={styles.modalCloseText}>닫기</Text>
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
                  <Text style={styles.modalTitle}>성경 종류</Text>
                  <ScrollView style={styles.modalList}>
                    {VERSION_OPTIONS.map((version) => (
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
                          {version.label} ({version.id})
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </ScrollView>
                  <TouchableOpacity
                    style={styles.modalClose}
                    onPress={() => setVersionModalOpen(false)}
                  >
                    <Text style={styles.modalCloseText}>닫기</Text>
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
                  {selectedBook?.ko_name ? `${selectedBook.ko_name} 장 선택` : "장 선택"}
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
                          {num}장
                        </Text>
                      </TouchableOpacity>
                    ))}
                    {!chapterOptions.length && (
                      <Text style={styles.empty}>장 목록을 불러오지 못했습니다.</Text>
                    )}
                  </View>
                </ScrollView>
                <TouchableOpacity
                  style={styles.modalClose}
                  onPress={() => setChapterModalOpen(false)}
                >
                  <Text style={styles.modalCloseText}>닫기</Text>
                </TouchableOpacity>
              </View>
            </View>
          </Modal>
          </ScrollView>
          <View style={styles.tabsBar}>
            <View style={styles.tabs}>
              {TABS.map((tab) => (
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
  }
});
