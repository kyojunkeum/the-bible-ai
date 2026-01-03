📘 TheBibleAI – Bible Text ETL & AI Foundation

본 프로젝트는 성경전서 개역한글판(KRV) 본문을 합법적 허락 범위 내에서 수집·정규화하여 DB화하고,
이를 기반으로 성경 읽기 / 검색 / AI 상담 기능을 구현하기 위한 데이터 파이프라인(ETL) 및 기반 구조를 제공합니다.

1. 프로젝트 목적

성경 본문을 DB 정본(Source of Truth) 으로 관리

AI가 본문을 생성하지 않고, DB에서만 인용하도록 구조적 안전장치 마련

크롤링 → 정규화 → 적재 → 검증까지 재현 가능한 단일 파이프라인 구축

장기적으로:

모바일 성경 앱

AI 상담 챗

오프라인 캐시 / 검색 / RAG 기반 인용
의 기반 데이터로 활용

2. 핵심 원칙 (중요)

본문 무결성

성경 본문은 임의 수정·요약·의역하지 않음

DB에 저장된 텍스트만 “성경 본문”으로 사용

크롤링 최소화

장(Chapter) 단위

저부하(요청 간 딜레이)

1회성 데이터 이관(Migration) 성격

재시작 가능

이미 적재된 장은 자동 스킵

중단 후 재실행 가능

법·정책 준수

개역한글판(KRV) 사용

출처 명시

허락된 범위 내 사용

3. 디렉토리 구조
TheBibleAI/
├─ api/                        # FastAPI 서버
├─ db/                         # DB 스키마 및 seed
│  ├─ 00_extensions.sql
│  ├─ 10_schema.sql
│  ├─ 20_indexes.sql
│  ├─ 40_seed_version.sql
│  └─ 41_seed_books.sql
│
├─ etl/                        # 본문 수집/적재 파이프라인
│  ├─ config.py                # DB/크롤링 설정
│  ├─ utils.py                 # 정규화/해시/딜레이
│  ├─ db.py                    # DB 접근/UPSERT
│  ├─ crawler.py               # 요청/파싱
│  └─ run_etl.py               # 메인 실행
│
├─ requirements.txt
├─ docs/
│  └─ DETAILED_DESIGN.md        # 상세 설계 명세서
└─ README.md

4. 데이터베이스 개요
주요 테이블

bible_version : 번역본 메타 (예: KRV)

bible_book : 66권 책 메타 (장 수 포함)

bible_verse : 절 단위 본문 (정본)

bible_chapter_hash : 장 단위 무결성 해시

정본 원칙

bible_verse가 유일한 본문 진실

AI/검색/앱은 이 테이블만 참조

5. 실행 환경

OS: Ubuntu (WSL)

DB: PostgreSQL (Docker)

Python: 3.12

패키지 관리: venv

가상환경 설정
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

6. ETL 실행 방법

⚠️ 실행 전 crawler.py의 URL 패턴과 DOM 선택자는 실제 사이트 구조에 맞게 구현해야 합니다.

source .venv/bin/activate
python etl/run_etl.py

동작 흐름

책/장 메타 조회

장 단위 HTML 요청

본문 파싱

절 단위 UPSERT

장 해시 계산 및 저장

다음 장으로 이동

7. 안전장치 및 제약

병렬 실행 ❌

크롤링 중 정규화 규칙 변경 ❌

본문 생성/보정 ❌

이미 적재된 장 재수집 ❌

8. 검증 쿼리 예시
-- 장 커버리지
SELECT COUNT(DISTINCT book_id, chapter)
FROM bible_verse WHERE version_id='krv';

-- 구약/신약 장 수 확인
SELECT testament, COUNT(DISTINCT book_id)
FROM bible_book WHERE version_id='krv'
GROUP BY testament;

9. 향후 확장 계획

FTS + Trigram 검색 API

AI 상담 챗 (DB 기반 인용 강제)

오프라인 캐시

다중 번역본(version_id 확장)

RAG 기반 주제별 말씀 추천

10. 라이선스 및 고지

사용 본문: 성경전서 개역한글판

번역 출처: 대한성서공회

본문은 DB에 원문 그대로 저장되며, 임의 수정하지 않습니다.

11. 상태

 DB 스키마 구축

 Seed 데이터 완료

 ETL 구조 완성

 사이트별 DOM 파서 구현

 전체 본문 적재

 검증 리포트 작성

12. 문서

- 상세 설계 명세서: docs/DETAILED_DESIGN.md

13. Web/Mobile MVP

Web (React + Vite)

- 위치: web/
- 실행(패키지 설치 필요):
  - npm install
  - npm run dev
- API 주소 설정: VITE_API_BASE (예: http://localhost:9000)

Mobile (React Native + Expo)

- 위치: mobile/
- 실행(패키지 설치 필요):
  - npm install
  - npm start
- API 주소 설정: EXPO_PUBLIC_API_BASE (예: http://<WSL_IP>:9000)
