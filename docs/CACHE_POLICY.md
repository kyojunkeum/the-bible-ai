# 앱 캐시 정책

## 공통 원칙

- 캐시 키: `chapter:{version_id}:{book_id}:{chapter}`
- 캐시 단위: 장(Chapter)
- 해시 검증: 서버 응답의 `content_hash`가 캐시의 `content_hash`와 다르면 캐시를 갱신

## Web (React)

- 저장소: `localStorage`
- LRU 인덱스 키: `chapter_cache_index`
- 최대 장 수: 200장
- 실패 시 동작: 서버 요청 실패 시 캐시 데이터로 대체 표시

## Mobile (React Native)

- 저장소: 메모리(Map) 기반
- 최대 장 수: 200장
- 실패 시 동작: 서버 요청 실패 시 캐시 데이터로 대체 표시

> 참고: 모바일은 현재 메모리 캐시이므로 앱 재시작 시 캐시가 초기화됩니다.
