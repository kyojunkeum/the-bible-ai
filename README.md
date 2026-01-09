## 📘 TheBibleAI (서비스명: 평안)
Bible Text ETL & Citation-Safe AI Foundation

TheBibleAI는 성경전서 개역한글판(KRV) 과 WEB(World English Bible Classic) 본문을 합법적 허락 범위 내에서 수집·정규화·검증하여 DB 정본(Source of Truth)으로 구축하고,
이를 기반으로 성경 읽기 · 검색 · 인용 강제형 AI 상담을 구현하기 위한 ETL + API + AI 기반 구조를 제공합니다.

본 프로젝트의 핵심은 AI가 성경 본문을 “생성하지 않고”, 오직 DB에 저장된 정본만을 정확히 인용하도록 구조적으로 강제하는 데 있습니다.

## 🎯 프로젝트 목적

성경 본문을 DB 정본(Source of Truth)으로 단일 관리

AI가 임의로 말씀을 생성·요약·변형하지 못하도록 구조적 안전장치 구현

크롤링 → 정규화 → 적재 → 무결성 검증까지 재현 가능한 ETL 파이프라인 구축

API 중심 구조로 Web / Mobile / 기타 UI를 완전히 분리

## 장기 활용 목표

📱 모바일 성경 앱

💬 성경 인용 강제형 AI 상담 챗

📦 오프라인 캐시 / 검색

🔍 FTS + Vector 기반 의미 검색

📚 RAG 기반 주제별 말씀 추천의 기반 데이터

## 🔑 핵심 설계 원칙 (중요)
1. 본문 무결성 (Source of Truth)

성경 본문은 절대 수정·요약·의역하지 않음

DB에 저장된 텍스트만 “성경 본문”으로 취급

AI, 검색, 앱, 상담은 모두 DB 정본만 참조

bible_verse 테이블이 유일한 진실

2. AI 인용 안전성 (Citation-Safe AI)

AI는 성경 본문을 생성하지 않음

모든 인용은:

DB 조회

원문 텍스트 1:1 검증

인용 포맷 강제

LLM이 인용을 왜곡·변형해도 서버에서 강제 수정

3. UI / 로직 완전 분리

Web / Mobile은 UI 전용

모든 판단·검색·AI 제어는 FastAPI 서버에서만 수행

| 구분         | 역할              |
| ---------- | --------------- |
| Web / App  | 입력·표시(UI)       |
| API Server | 검색·인용·상담·AI 판단  |
| DB         | 성경 정본 및 메타      |
| Redis      | 상담 세션 메타/TTL/일일 제한 |
| Ollama     | LLM / Embedding |

4. 서버가 최종 집행자

프론트가 보내는 토글/플래그는 참고만 하며, 저장 여부·턴 제한·만료는 서버가 최종 강제


장(Chapter) 단위 수집

저부하 요청 (딜레이 적용)

1회성 Migration 성격

이미 적재된 장은 자동 스킵

중단 후 재실행 가능

## 📁 디렉토리 구조

```text
TheBibleAI/
├─ api/                  # FastAPI 서버
├─ db/                   # DB 스키마 및 Seed
│  ├─ 00_extensions.sql
│  ├─ 10_schema.sql
│  ├─ 20_indexes.sql
│  ├─ 40_seed_version.sql
│  └─ 41_seed_books.sql
├─ etl/                  # ETL 파이프라인
│  ├─ config.py
│  ├─ utils.py
│  ├─ db.py
│  ├─ crawler.py
│  └─ run_etl.py
├─ docs/
│  └─ DETAILED_DESIGN.md
├─ web/
├─ mobile/
├─ requirements.txt
└─ README.md
```

## ✅ 상담/저장 정책 요약
- 익명 체험: store_messages는 항상 false 강제 (프론트 값 무시)
- 로그인 사용자: user_settings.store_messages 기준으로 저장 여부 결정
- 상담 세션: Redis에서 TTL/턴 제한/턴 카운트 관리
- 익명 일일 제한: KST 기준으로 device_id (없으면 IP) 단위로 일일 턴 제한
- 응답 메타에 남은 턴/일일 제한 정보 포함


## 데이터베이스 개요
주요 테이블

bible_version : 번역본 메타 (예: KRV)

bible_book : 66권 책 메타 (장 수, 약어, 구분)

bible_verse : 절 단위 본문 (정본)

bible_chapter_hash : 장 단위 무결성 해시

bible_verse_window : Vector 검색용 윈도우 인덱스

user_settings : 대화 저장 설정 (서버 강제)

oauth_account / auth_refresh_token : Google OAuth 및 JWT 리프레시 토큰 관리

정본 원칙

bible_verse만 본문 진실

검색 / AI / 앱은 절대 외부 텍스트 사용 금지

## ⚙ 실행 환경

OS: Ubuntu (WSL)

DB: PostgreSQL (Docker)

Python: 3.12

패키지 관리: venv

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

## 🐳 Docker 빠른 시작
docker compose up -d --build

이미 생성된 DB에 OAuth 테이블을 추가해야 하는 경우:
docker compose exec postgres psql -U bible -d bible_app -f /docker-entrypoint-initdb.d/90_oauth_schema.sql

이미 생성된 DB에 OpenAI 설정 컬럼을 추가해야 하는 경우:
docker compose exec postgres psql -U bible -d bible_app -f /docker-entrypoint-initdb.d/75_user_settings_llm.sql

## 🌐 Web / 📱 Mobile 실행
- Web: `cd web && npm install && npm run dev`
- Mobile(Expo): `cd mobile && npm install && npm run start`

## 🚚 ETL 실행 방법

⚠️ 실행 전 crawler.py의 URL 패턴 및 DOM 선택자는
실제 허락된 사이트 구조에 맞게 구현되어야 합니다.

source .venv/bin/activate
python etl/run_etl.py

ETL 동작 흐름

책/장 메타 조회

장 단위 HTML 요청

본문 파싱

절 단위 UPSERT

장 해시 계산 및 저장

다음 장으로 이동

## 🛡 안전장치 및 제약

병렬 실행 ❌

크롤링 중 정규화 규칙 변경 ❌

본문 생성/보정 ❌

이미 적재된 장 재수집 ❌

🔍 검증 쿼리 예시
-- 장 커버리지
SELECT COUNT(DISTINCT book_id, chapter)
FROM bible_verse
WHERE version_id='krv';

-- 구약/신약 권 수 확인
SELECT testament, COUNT(DISTINCT book_id)
FROM bible_book
WHERE version_id='krv'
GROUP BY testament;

## 🤖 API 기능 개요
성경 조회 / 검색

책 목록 조회

장 본문 조회

키워드 검색 (FTS + Trigram)

pgvector 기반 의미 검색

인증/설정
- JWT access/refresh 기반 인증 (웹/앱 공용)
- Google OAuth PKCE 로그인 (start/exchange)
- 사용자 설정 저장/조회 (store_messages)
- 사용자별 OpenAI API 연동 (openai_citation_enabled + api_key)

## 상담 챗 (핵심)

대화 상태 관리 + 요약

위기(자해/자살) 탐지 → 고정 응답

구절 직접 입력 시 → 즉시 구절 조회

필요 시에만 성경 구절 자동 인용

인용 텍스트 DB 원문 1:1 검증

AI는 “언제, 왜, 어떤 구절을 인용했는지” 항상 설명 가능

익명 체험 제한
- TTL 및 턴 제한(서버/Redis 관리)
- KST 기준 일일 턴 제한

## 🔐 인증 & OAuth (JWT + PKCE)
- JWT access/refresh 토큰 발급
- refresh 시 기존 refresh 토큰 폐기 후 재발급
- Google OAuth는 PKCE 방식 (client_secret 없이 동작 가능)
- 리다이렉트 예시
  - Web: `https://<YOUR_WEB_DOMAIN>` (현재 웹 앱의 origin)
  - Mobile: `thebibleai://oauth/google`

## 🤖 OpenAI 연동 (사용자별 BYOK)
- 기본 상담은 로컬 LLM(Ollama) 사용
- 사용자 설정에서 `openai_citation_enabled=true` + API 키 저장 시, 상담 관련 LLM 호출은 OpenAI 사용
- OpenAI 실패 시 로컬 LLM로 자동 폴백
- 서버 전역 스위치 `OPENAI_CITATION_ENABLED=1`이 켜져 있어야 동작
- OpenAI API 키는 OpenAI 또는 OpenAI 호환 Gateway에서만 유효하며, 다른 LLM 제공자는 별도 키/연동 필요

설정 예시 (로그인 필요):
- `PATCH /v1/users/me/settings`
```json
{
  "openai_citation_enabled": true,
  "openai_api_key": "sk-..."
}
```

LLM Gateway 사용 시:
- `OPENAI_BASE_URL`을 Gateway 엔드포인트로 설정

키 삭제:
```json
{
  "openai_api_key": ""
}
```

## ⚙️ 주요 환경 변수
- `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SEC`
- `REDIS_URL`
- `ANON_CHAT_TTL_SEC`, `ANON_CHAT_TURN_LIMIT`, `ANON_DAILY_TURN_LIMIT`
- `JWT_SECRET`, `JWT_ISSUER`, `JWT_AUDIENCE`, `JWT_ACCESS_TTL_SEC`, `JWT_REFRESH_TTL_SEC`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (선택, 없으면 OAuth 비활성)
- `OPENAI_CITATION_ENABLED`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TIMEOUT_SEC`, `OPENAI_BASE_URL`
- `OPENAI_KEY_ENCRYPTION_SECRET` (설정 시 DB에 저장되는 사용자 키를 암호화, 미설정 시 평문 저장)
- `KOBERT_MODEL_ID`, `RERANK_CANDIDATES`, `RERANK_TOP_N`
- `VECTOR_ENABLED`, `VECTOR_WINDOW_SIZE`

## 🔮 향후 확장 계획

다중 번역본(version_id 확장)

RAG 기반 주제별 말씀 추천


환경 변수:

VECTOR_WINDOW_SIZE

VECTOR_WINDOW_STRIDE

OLLAMA_EMBED_MODEL

옵션:

VECTOR_ENABLED=1

RERANK_MODE는 현재 ko-bert 고정(환경변수로 변경하지 않음)

## 📜 라이선스 및 고지

사용 본문: 성경전서 개역한글판 / WEB

번역 출처: 대한성서공회 / WEB

본문은 DB에 원문 그대로 저장되며 임의 수정하지 않습니다

## 🚧 프로젝트 상태

DB 스키마 구축 ✅

Seed 데이터 완료 ✅

ETL 구조 완성 ✅

사이트별 DOM 파서 구현 🔄

전체 본문 적재 🔄

검증 리포트 작성 🔄

## 🌐 Web / Mobile MVP
Web (React + Vite)

위치: web/

npm install
npm run dev


API 주소: VITE_API_BASE=http://localhost:9000

Mobile (React Native + Expo)

위치: mobile/

npm install
npm start


API 주소:
EXPO_PUBLIC_API_BASE=http://<WSL_IP>:9000

## ✨ 한 줄 요약

TheBibleAI는 “성경 본문을 생성하지 않는 AI”를 만들기 위한
데이터·API·인용 안전성 중심의 기반 시스템입니다.
