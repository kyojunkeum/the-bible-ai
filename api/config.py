import os

DB = {
    "host": os.getenv("BIBLE_DB_HOST", "localhost"),
    "port": int(os.getenv("BIBLE_DB_PORT", "5432")),
    "dbname": os.getenv("BIBLE_DB_NAME", "bible_app"),
    "user": os.getenv("BIBLE_DB_USER", "bible"),
    "password": os.getenv("BIBLE_DB_PASSWORD", "biblepassword"),
}

API_TITLE = "TheBibleAI API"
API_VERSION = "0.1.0"
