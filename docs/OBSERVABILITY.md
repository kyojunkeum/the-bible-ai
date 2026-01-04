# 관측/로그 정책

## 로그 저장 위치

- 파일: `logs/events.log`
- 형식: JSON Lines (한 줄에 하나의 이벤트)

## 공통 규칙

- `conversation_id`는 해시 처리되어 저장됩니다.
- 사용자 메시지 본문은 로그에 저장하지 않습니다.

## 주요 이벤트 타입

- `search_latency`, `search_slow`, `search_zero`
- `retrieval_latency`, `retrieval_slow`, `retrieval_zero`
- `embedding_latency`, `embedding_error`
- `vector_latency`, `vector_zero`
- `llm_latency`, `llm_slow`, `llm_error`
- `chat_created`, `chat_message`, `chat_response`, `chat_crisis`, `chat_deleted`
- `verse_cited`
- `citation_attempt`, `retrieval_candidates`, `citation_selected`, `citation_failure`

`retrieval_candidates` 이벤트 추가 필드:
- `rerank_order_before`, `rerank_order_after`, `rerank_delta`

## 예시

```json
{"event_type":"chat_response","ts":"2024-01-01T00:00:00Z","conversation_id":"<hashed>","citations_count":1,"need_verse":true,"llm_ok":true}
```
