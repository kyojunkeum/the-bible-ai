## 📘 TheBibleAI
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

구분	역할
Web / App	입력·표시(UI)
API Server	검색·인용·상담·AI 판단
DB	성경 정본 및 메타
Ollama	LLM / Embedding
4. 크롤링 최소화 · 재현성 보장

장(Chapter) 단위 수집

저부하 요청 (딜레이 적용)

1회성 Migration 성격

이미 적재된 장은 자동 스킵

중단 후 재실행 가능

## 📁 디렉토리 구조
TheBibleAI/
├─ api/                  # FastAPI 서버 (검색 / 상담 / 인용)
├─ db/                   # DB 스키마 및 Seed
│  ├─ 00_extensions.sql
│  ├─ 10_schema.sql
│  ├─ 20_indexes.sql
│  ├─ 40_seed_version.sql
│  └─ 41_seed_books.sql
├─ etl/                  # 본문 수집/정규화/적재 파이프라인
│  ├─ config.py
│  ├─ utils.py
│  ├─ db.py
│  ├─ crawler.py
│  └─ run_etl.py
├─ docs/
│  └─ DETAILED_DESIGN.md  # 상세 설계 명세서
├─ web/                  # Web UI (React + Vite)
├─ mobile/               # Mobile UI (React Native + Expo)
├─ requirements.txt
└─ README.md

## 데이터베이스 개요
주요 테이블

bible_version : 번역본 메타 (예: KRV)

bible_book : 66권 책 메타 (장 수, 약어, 구분)

bible_verse : 절 단위 본문 (정본)

bible_chapter_hash : 장 단위 무결성 해시

bible_verse_window : Vector 검색용 윈도우 인덱스

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

## 상담 챗 (핵심)

대화 상태 관리 + 요약

위기(자해/자살) 탐지 → 고정 응답

구절 직접 입력 시 → 즉시 구절 조회

필요 시에만 성경 구절 자동 인용

인용 텍스트 DB 원문 1:1 검증

AI는 “언제, 왜, 어떤 구절을 인용했는지” 항상 설명 가능

## 🔮 향후 확장 계획

다중 번역본(version_id 확장)

RAG 기반 주제별 말씀 추천


환경 변수:

VECTOR_WINDOW_SIZE

VECTOR_WINDOW_STRIDE

OLLAMA_EMBED_MODEL

옵션:

VECTOR_ENABLED=1

RERANK_MODE=llm | ko-bert | off

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