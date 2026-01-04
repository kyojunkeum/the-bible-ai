# ERD (텍스트 요약)

## 테이블 요약

### bible_version
- PK: version_id
- 주요 컬럼: name, publisher, copyright_notice

### bible_book
- PK: (version_id, book_id)
- FK: version_id -> bible_version.version_id
- 주요 컬럼: osis_code, ko_name, abbr, chapter_count, testament

### bible_verse
- PK: (version_id, book_id, chapter, verse)
- FK: (version_id, book_id) -> bible_book
- 주요 컬럼: text, normalized, search_vector

### bible_chapter_hash
- PK: (version_id, book_id, chapter)
- FK: (version_id, book_id) -> bible_book
- 주요 컬럼: verse_count, content_hash

### search_synonym
- PK: (term, synonym)
- 주요 컬럼: weight, created_at

### bible_verse_window
- PK: (version_id, book_id, chapter, verse_start, verse_end)
- FK: (version_id, book_id) -> bible_book
- 주요 컬럼: text, normalized, embedding

### app_user
- PK: user_id
- 주요 컬럼: email, password_hash, created_at, last_login

### user_session
- PK: session_token
- FK: user_id -> app_user.user_id
- 주요 컬럼: device_id, created_at, expires_at, last_seen

### auth_login_attempt
- PK: (scope, scope_key)
- 주요 컬럼: fail_count, blocked_until, last_failed_at

### bible_bookmark
- PK: (device_id, version_id, book_id, chapter, verse)
- FK: (version_id, book_id, chapter, verse) -> bible_verse
- 주요 컬럼: user_id, created_at

### bible_memo
- PK: (device_id, version_id, book_id, chapter, verse)
- FK: (version_id, book_id, chapter, verse) -> bible_verse
- 주요 컬럼: user_id, memo_text, created_at, updated_at

### chat_conversation
- PK: conversation_id
- 주요 컬럼: device_id, locale, version_id, store_messages, summary, created_at, updated_at

### chat_message
- PK: id
- FK: conversation_id -> chat_conversation.conversation_id
- 주요 컬럼: role, content, created_at

## 관계 요약

- bible_version 1 --- n bible_book
- bible_book 1 --- n bible_verse
- bible_book 1 --- n bible_chapter_hash
- app_user 1 --- n user_session
- app_user 1 --- n auth_login_attempt (scope=account)
- chat_conversation 1 --- n chat_message
