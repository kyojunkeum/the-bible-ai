# etl/build_vector_index.py
import os
import time
from typing import List, Tuple

import psycopg2
import requests
from psycopg2.extras import execute_values

from etl.config import DB, VERSION_ID
from etl.db import fetch_books
from etl.utils import normalize_text


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_TIMEOUT_SEC = float(os.getenv("OLLAMA_TIMEOUT_SEC", "20"))
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))

WINDOW_SIZE = int(os.getenv("VECTOR_WINDOW_SIZE", "5"))
WINDOW_STRIDE = int(os.getenv("VECTOR_WINDOW_STRIDE", "1"))
BATCH_SIZE = int(os.getenv("VECTOR_BATCH_SIZE", "20"))

UPSERT_WINDOW_SQL = """
INSERT INTO bible_verse_window
(version_id, book_id, chapter, verse_start, verse_end, text, normalized, embedding)
VALUES %s
ON CONFLICT (version_id, book_id, chapter, verse_start, verse_end)
DO UPDATE SET
  text = EXCLUDED.text,
  normalized = EXCLUDED.normalized,
  embedding = EXCLUDED.embedding,
  updated_at = now();
"""


def _vector_literal(values: List[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


def _embed_text(text: str) -> List[float] | None:
    payload = {"model": OLLAMA_EMBED_MODEL, "prompt": text}
    try:
        res = requests.post(f"{OLLAMA_URL}/api/embeddings", json=payload, timeout=OLLAMA_TIMEOUT_SEC)
        res.raise_for_status()
        data = res.json()
    except requests.RequestException:
        return None
    embedding = data.get("embedding")
    if not isinstance(embedding, list):
        return None
    if EMBEDDING_DIM and len(embedding) != EMBEDDING_DIM:
        return None
    return embedding


def _fetch_chapter_verses(conn, version_id: str, book_id: int, chapter: int) -> List[Tuple[int, str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT verse, text
            FROM bible_verse
            WHERE version_id = %s AND book_id = %s AND chapter = %s
            ORDER BY verse
            """,
            (version_id, book_id, chapter),
        )
        return cur.fetchall()


def _build_windows(verses: List[Tuple[int, str]]) -> List[Tuple[int, int, str, str]]:
    windows = []
    if len(verses) < WINDOW_SIZE:
        return windows
    for idx in range(0, len(verses) - WINDOW_SIZE + 1, WINDOW_STRIDE):
        slice_verses = verses[idx : idx + WINDOW_SIZE]
        verse_start = slice_verses[0][0]
        verse_end = slice_verses[-1][0]
        text = " ".join(text for _v, text in slice_verses)
        normalized = normalize_text(text)
        windows.append((verse_start, verse_end, text, normalized))
    return windows


def _flush_windows(conn, rows: List[Tuple]):
    if not rows:
        return
    with conn.cursor() as cur:
        execute_values(
            cur,
            UPSERT_WINDOW_SQL,
            rows,
            template="(%s,%s,%s,%s,%s,%s,%s,%s::vector)",
        )
    conn.commit()


def main():
    with psycopg2.connect(**DB) as conn:
        books = fetch_books(conn, VERSION_ID)
        for book_id, _osis, chapter_count in books:
            for chapter in range(1, chapter_count + 1):
                verses = _fetch_chapter_verses(conn, VERSION_ID, book_id, chapter)
                windows = _build_windows(verses)
                batch = []
                for verse_start, verse_end, text, normalized in windows:
                    embedding = _embed_text(normalized or text)
                    if not embedding:
                        continue
                    batch.append(
                        (
                            VERSION_ID,
                            book_id,
                            chapter,
                            verse_start,
                            verse_end,
                            text,
                            normalized,
                            _vector_literal(embedding),
                        )
                    )
                    if len(batch) >= BATCH_SIZE:
                        _flush_windows(conn, batch)
                        batch = []
                        time.sleep(0.2)
                if batch:
                    _flush_windows(conn, batch)
                time.sleep(0.2)


if __name__ == "__main__":
    main()
