# OpenAPI 요약

FastAPI가 `/openapi.json` 및 `/docs`를 자동 제공하므로 실행 후 확인할 수 있습니다.

## Bible API

- GET `/v1/bible/{version_id}/books`
  - 설명: 책 목록 조회
- GET `/v1/bible/{version_id}/books/{book_id}/chapters/{chapter}`
  - 설명: 장 본문 조회(해시 포함)
- GET `/v1/bible/{version_id}/ref?book=...&chapter=...&verse=...`
  - 설명: 참조 파서 기반 단일 절 조회
- GET `/v1/bible/{version_id}/search?q=...&limit=...&offset=...`
  - 설명: FTS + 부분일치 검색

## Chat API

- POST `/v1/chat/conversations`
  - 설명: 세션 생성
  - 요청 예시:
    ```json
    { "device_id": "web", "locale": "ko-KR", "version_id": "krv", "store_messages": false }
    ```
- GET `/v1/chat/conversations/{conversation_id}`
  - 설명: 대화 조회(옵트인 저장 시 DB, 아니면 메모리 기반)
- DELETE `/v1/chat/conversations/{conversation_id}`
  - 설명: 대화 삭제(저장된 경우 DB에서 삭제)
- POST `/v1/chat/conversations/{conversation_id}/messages`
  - 설명: 메시지 전송 및 응답 생성

## 공통 오류 포맷

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
