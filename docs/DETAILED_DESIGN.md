# 말씀동행 상세 설계 명세서 (Detailed Design Specification)

## 0. 설계 원칙 요약

1. 성경 본문은 DB 정본(SoT), 앱은 캐시(읽기 최적화)
2. LLM은 대화 생성자, 성경 인용은 검색 기반(grounded)
3. AI는 설교/강론이 아니라 대화(공감-질문-정리-선택적 인용)
4. 인용 구절은 DB에 존재하는 본문만 가능(임의 생성 금지)
5. 개인정보/상담 내용은 최소 수집·최소 전달·선택 삭제

> 참고(법적 근거 확인): 대한성서공회 FAQ에 따르면 개역한글판은 저작재산권 보호기간 경과로 저작권료 없이 사용 가능하나, 성명표시권/동일성유지권 등 인격권 준수(출처 명시·무단 변경 금지)가 필요합니다.

---

## 1. 시스템 구성(논리/물리 아키텍처)

### 1.1 논리 아키텍처(핵심 컴포넌트)

- Mobile App (Flutter / RN)
  - Bible Reader UI, Search UI, Chat UI
  - 로컬 캐시(장 단위), 북마크/메모 로컬 저장
- Backend API (FastAPI 권장)
  - Bible API(조회/검색)
  - Chat Orchestrator(세션, 메모리, 안전/정책)
  - Verse Retrieval(구절 검색/선정)
- Bible DB (PostgreSQL + FTS)
  - verse 단위 저장, 장 단위 해시
  - 검색 인덱스(FTS + 부분일치)
- Conversation Store
  - 기본: 서버 저장 최소화(옵션화)
  - 운영/품질 개선용으로 익명화 로그 최소 저장(옵션)
- LLM Gateway
  - 외부 LLM API 호출, 프롬프트 템플릿/정책 적용
  - 장애 시 degrade 모드(인용 없이 대화, 혹은 상담 제한)

### 1.2 물리 배포(권장)

- 단일 VPC/클라우드 또는 온프레미스
  - api (FastAPI) + postgres + redis(선택) + observability(선택)
- 확장:
  - 검색 부하 증가 시: OpenSearch 교체 가능 구조(비기능 요구사항 반영)

---

## 2. 데이터 설계

## 2.1 Bible DB 스키마(정본)

### 2.1.1 테이블: bible_version

- version_id (PK) : 예) krv
- name : 성경전서 개역한글판
- publisher : 대한성서공회
- copyright_notice : 고지 문구(앱 표시용)
- created_at

### 2.1.2 테이블: bible_book

- version_id (FK)
- book_id (PK, int) : 정렬용(1~66)
- osis_code : 예) GEN, EXO...
- ko_name : 창세기
- abbr : 창
- chapter_count

### 2.1.3 테이블: bible_verse

- PK: (version_id, book_id, chapter, verse)
- text (본문)
- normalized (검색용 정규화: 공백/특수문자 처리)
- search_vector (tsvector, GENERATED ALWAYS AS to_tsvector('simple', normalized))
- created_at, updated_at

### 2.1.4 테이블: bible_chapter_hash

- PK: (version_id, book_id, chapter)
- content_hash (sha256 등)
- verse_count
- 목적:
  - 앱 캐시 무결성 검증/버전업 시 변경 감지

### 2.1.5 검색 인덱스(FTS)

- Postgres:
  - search_vector 컬럼(예: bible_verse.search_vector)
  - GIN 인덱스
- 부분일치:
  - pg_trgm(trigram) 기반 normalized 보조 인덱스(옵션)
- 주의:
  - unaccent 확장은 설치되어 있으나, 기본 검색 파이프라인에는 적용하지 않음(필요 시 별도 설계)

---

## 2.2 사용자 로컬 저장(앱)

### 2.2.1 로컬 캐시(장 단위)

- 키: (version_id, book_id, chapter)
- 값:
  - 본문(절 배열)
  - content_hash(서버값과 비교)
  - cached_at
- 정책:
  - LRU + 용량 제한(예: 최대 200장)
  - 오프라인 읽기 보장

### 2.2.2 북마크/메모

- 북마크: (version_id, book_id, chapter, verse)
- 메모: 동일 키 + memo_text, created_at
- 기본은 로컬만(요구사항 FR-042)
- 확장: 계정 도입 시 동기화 옵션

---

## 2.3 상담 데이터(서버 저장 최소화)

권장 2단계 설계:

- MVP 기본값: 서버 저장 최소/비식별
  - conversation_id만 서버에서 발급
  - 대화 전문 저장은 사용자 선택(Opt-in)
- 품질 개선/안전 로그(최소 저장)
  - 구절 인용 이벤트(어떤 구절이 어떤 시점에 사용되었는지)
  - LLM 호출 성공/실패, 지연시간, 토큰 사용량
  - 사용자 메시지 전문은 기본 저장하지 않음(가능하면)

---

## 3. API 상세 설계

## 3.1 Bible API

### 3.1.0 공통 오류 응답 형식

- 오류 응답은 다음 형식을 사용한다:

```json
{
  "error": {
    "code": "http_error",
    "message": "chapter not found"
  }
}
```

```json
{
  "error": {
    "code": "validation_error",
    "message": "invalid request",
    "details": []
  }
}
```

### 3.1.1 책/장/절 조회

- GET /v1/bible/{version_id}/books
  - 응답: book 목록(정렬, 장 수 포함)
  - 예시 응답:

```json
{
  "items": [
    {
      "book_id": 1,
      "osis_code": "GEN",
      "ko_name": "창세기",
      "abbr": "창",
      "chapter_count": 50,
      "testament": "OT"
    }
  ]
}
```
- GET /v1/bible/{version_id}/books/{book_id}/chapters/{chapter}
  - 응답:
    - content_hash
    - verses: [{verse:int, text:string}]
  - 예시 응답:

```json
{
  "content_hash": "0f9b7f...",
  "verses": [
    {"verse": 1, "text": "태초에 하나님이 천지를 창조하시니라"},
    {"verse": 2, "text": "땅이 혼돈하고 공허하며"}
  ]
}
```
- GET /v1/bible/{version_id}/ref?book=창세기&chapter=1&verse=1
  - 입력 다양성(창1:1) 파싱 지원(서버 ref 파서에서 normalize)
  - 사용자 직접 인용 요청은 LLM 생성 없이 ref 파서 + DB 검증으로 처리
  - 입력 예시:
    - 창1:1
    - 창세기 1장 1절
    - GEN 1:1
  - 예시 응답:

```json
{
  "book_id": 1,
  "book_name": "창세기",
  "chapter": 1,
  "verse": 1,
  "text": "태초에 하나님이 천지를 창조하시니라"
}
```

### 3.1.2 검색

- GET /v1/bible/{version_id}/search?q=키워드&limit=50&offset=0
  - 응답:
    - total
    - items: [{book_id, book_name, chapter, verse, snippet, text}]
  - 예시 응답:

```json
{
  "total": 2,
  "items": [
    {
      "book_id": 19,
      "book_name": "시편",
      "chapter": 23,
      "verse": 1,
      "snippet": "여호와는 나의 목자시니",
      "text": "여호와는 나의 목자시니 내게 부족함이 없으리로다"
    }
  ]
}
```
  - 구현:
    - 1차: FTS 랭킹(search_vector 기반)
    - 2차: 부분일치 보정(짧은 키워드/오타)
    - 정규화 규칙은 ETL normalize_text()와 동일해야 함
    - unaccent는 기본 파이프라인에 적용하지 않음(필요 시 별도 확장)

---

## 3.2 Chat API (상담 오케스트레이션)

### 3.2.1 세션 생성

- POST /v1/chat/conversations
  - 요청: { device_id?, locale, version_id="krv" }
  - 응답: { conversation_id, created_at }

### 3.2.2 메시지 전송(핵심)

- POST /v1/chat/conversations/{conversation_id}/messages
  - 요청:

    ```json
    {
      "user_message":"요즘 불안해서 잠이 안 와요",
      "client_context":{
        "app_version":"1.0.0",
        "timezone":"Asia/Seoul",
        "offline_capable":true
      }
    }
    ```

  - 응답:

    ```json
    {
      "assistant_message":"...",
      "citations":[
        {"version_id":"krv","book_id":19,"chapter":23,"verse_start":1,"verse_end":2}
      ],
      "memory":{"mode":"recent+summary","recent_turns":8}
    }
    ```

### 3.2.3 대화 기록(옵션)

- GET /v1/chat/conversations/{conversation_id}
- DELETE /v1/chat/conversations/{conversation_id}
  - 삭제 가능 요구사항 반영(서버 저장이 있는 경우에만 실질 의미)

---

## 4. AI 상담 동작 설계(가장 중요한 부분)

## 4.1 오케스트레이션 단계(서버)

Step A. 입력 정제

- 욕설/위협/자해 등 안전 분류(규칙 + 모델)
- 개인식별정보(전화/주민/계좌 등) 최소화 마스킹(가능하면)

Step B. 메모리 구성

- 최근 N턴: 예) 8턴 (FR-030)
- 요약 메모리: 예) 800자 내외 (FR-031)
- 최종 입력 컨텍스트:
  - System Policy
  - Conversation Summary
  - Recent Turns
  - Current User Message

Step C. 구절 인용 필요성 판단(Gating)

- LLM에 바로 생성시키지 말고, 먼저 인용이 필요한지/어떤 주제인지 분류 프롬프트로 판단
- 출력: { need_verse: true/false, topics:[...], emotions:[...], risk_flags:[...] }

Step D. 구절 검색(Retrieval)

- need_verse=true인 경우에만 수행
- 검색 전략(권장):
  1. 키워드 기반: 사용자 메시지 + 요약에서 핵심 키워드 추출
  2. 토픽 기반: 불안/두려움/관계/상실/죄책감 등 → 주제 사전(룰)
  3. FTS 상위 K개(예: 20개) 가져오기
  4. Rerank(간단 LLM 또는 룰): 지금 상황에 위로/방향성이 있는가

Step E. 구절 포함 응답 생성(Grounded Generation)

- 최종 생성 프롬프트에는:
  - 선택된 구절 원문(절/본문)
  - 인용 규칙(절대로 없는 구절 만들지 마라)
  - 대화 톤(공감→질문→정리→선택적 말씀→실행 가능한 작은 제안)

Step F. 후처리 검증(필수)

- 응답에 인용이 포함되면:
  - 실제 DB 구절과 완전 일치하는지 검사(문자열 비교)
  - 불일치 시: 인용 제거 후 참조 링크 형태로 재작성 또는 재생성

Step G. 사용자 직접 인용 요청 처리(LLM 판단 최소화)

- 사용자 입력에 명시적 구절 요청이 포함되면(예: "창1:1", "창세기 1장 1절", "GEN 1:1"):\n  - LLM이 직접 book/chapter/verse를 생성하지 않는다\n  - 서버의 ref 파서가 입력을 정규화하고 DB로 검증 후 조회한다\n+- 흐름: 사용자 입력 -> ref 파서 -> DB 조회 -> 응답 반환

---

## 4.2 프롬프트 템플릿(요지)

### 4.2.1 인용 필요성 판단 프롬프트(초경량)

- 출력 JSON 강제:
  - need_verse (bool)
  - topics (list)
  - user_goal (string)
  - risk_flags (list)

### 4.2.2 상담 생성 프롬프트(핵심)

포함 요소:

- 설교 금지 / 단정 금지 / 질문 1~2개
- 조언은 선택지로 제시
- 구절은 최대 1~2개, 짧게, 자연스럽게
- 인용 시: (책 장:절) 표기 + 본문 그대로
- 위기(자해 등) 플래그 시: 안전 안내 우선(전문기관 권고)

---

## 4.3 메모리 요약 정책

- 최근 N턴(원문) + 요약 메모리(압축)
- 요약 트리거:
  - 메시지 수 > 30 또는 토큰 > 임계치
- 요약 내용(권장 필드):
  - 사용자 상황(객관)
  - 감정 상태
  - 반복되는 고민 주제
  - 사용자가 원한 것/싫어한 것(대화 선호)
  - 이미 제안한 실행 과제(중복 방지)

---

## 5. 무결성/저작권/고지(앱 화면 요구)

## 5.1 고지 페이지(필수)

- 번역본: 성경전서 개역한글판
- 대한성서공회 번역 명시
- 본문 임의 수정 금지 취지 고지

대한성서공회 FAQ는 개역한글판의 경우 저작권료 없이 사용 가능하나, 성명표시권/동일성유지권 준수 필요를 명시합니다.

---

## 6. 비기능 상세 설계

### 6.1 성능 목표(구체화)

- 장 조회:
  - 캐시 hit: 50ms~150ms
  - 캐시 miss(서버): P95 500ms 이내
- 검색:
  - P95 1초 이내(상위 50건)

### 6.2 안정성(장애 모드)

- LLM 장애:
  - 상담 제한 모드: 공감/정리/질문만 제공(구절 인용 OFF)
  - 사용자에게 현재 상담 기능이 원활하지 않음 안내
- DB 장애:
  - 캐시된 장은 계속 읽기 가능
  - 검색/인용 불가 안내

### 6.3 보안/프라이버시

- 전송 구간: TLS 필수
- 저장 최소화:
  - 기본: 대화 전문 저장 X
  - 로그는 익명화/집계 중심
- 대화 삭제는 서버 저장을 켠 사용자에게만 실효성 있음(정책 문구에 명확히)

---

## 7. 운영/관측(Observability) & 품질 지표

### 7.1 필수 메트릭

- Bible API:
  - 장 조회 latency, 캐시 hit ratio, 오류율
- Search:
  - 검색 latency, 결과 0건 비율(검색 실패율)
- Chat:
  - LLM latency, 실패율, 재시도율
  - 구절 인용 비율(너무 높으면 설교처럼 느껴질 위험)

### 7.2 이벤트 로그(최소)

- verse_cited 이벤트:
  - conversation_id(해시), book/chapter/verse, timestamp
- llm_error:
  - 에러 코드, 모델명, retry 횟수

---

## 8. 테스트/검증 계획(수용 기준과 연결)

### 8.1 기능 테스트

- 읽기/검색/오프라인
- 북마크/메모
- 세션 유지/요약 메모리 동작

### 8.2 핵심 안전 테스트(반드시)

- AI가 없는 구절을 지어내지 않는가?
  - 랜덤 질의 100개에 대해:
    - 인용 발생 시 DB와 100% 일치해야 함
- 항상 구절을 붙이지 않는가?
  - 일상 대화 50개 샘플에서 인용률 상한(예: 30% 이하)

### 8.3 UX 품질 테스트

- 상담이 설교로 인지되는지 사용자 테스트(정성)
- 질문/공감/요약이 자연스러운지(평가지표)

---

## 9. MVP 범위에 맞춘 구현 순서(추천)

1. Bible DB 적재 + 장 조회 API + 앱 캐시
2. Search API(FTS + 부분일치)
3. Chat 세션/메모리 + LLM 연동(인용 없이)
4. 인용 Gating + Retrieval + DB 일치 검증 붙이기(완성도 핵심)
5. 북마크/메모(로컬)
6. 관측/로그 최소 세팅

---

## 10. 산출물(개발팀 인계용 체크리스트)

- [ ] ERD(테이블/인덱스)
- [ ] OpenAPI(Swagger) 명세
- [ ] 프롬프트 템플릿 2종(게이팅/생성)
- [ ] 인용 검증 로직(문자열 일치 + ref 메타)
- [ ] 앱 캐시 정책(LRU/해시검증)
- [ ] 고지 페이지 문구(출처/동일성 유지)
