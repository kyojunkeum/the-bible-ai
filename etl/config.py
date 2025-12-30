# etl/config.py

DB = {
    "host": "localhost",   # Docker 포트 매핑 기준
    "port": 5432,
    "dbname": "bible_app",
    "user": "bible",
    "password": "biblepassword",
}

VERSION_ID = "krv"

# 요청 간 딜레이 (초) — 저부하
REQUEST_DELAY_SEC = 1.5

# 재시도 최대 횟수
MAX_RETRY = 3

# User-Agent (허락 메일에 명시한 서비스명/연락처)
USER_AGENT = "TheBibleAI/1.0 (contact: kyojunkeum@gmail.com)"

# (선택) 원본 HTML 저장 경로
RAW_HTML_DIR = "etl/_raw_html"

