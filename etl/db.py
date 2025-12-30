# etl/db.py
import psycopg2
from psycopg2.extras import execute_values

UPSERT_VERSE_SQL = """
INSERT INTO bible_verse
(version_id, book_id, chapter, verse, text, normalized)
VALUES %s
ON CONFLICT (version_id, book_id, chapter, verse)
DO UPDATE SET
  text = EXCLUDED.text,
  normalized = EXCLUDED.normalized,
  updated_at = now();
"""

UPSERT_CHAPTER_HASH_SQL = """
INSERT INTO bible_chapter_hash
(version_id, book_id, chapter, verse_count, content_hash)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (version_id, book_id, chapter)
DO UPDATE SET
  verse_count = EXCLUDED.verse_count,
  content_hash = EXCLUDED.content_hash,
  updated_at = now();
"""

def get_conn(cfg):
    return psycopg2.connect(**cfg)

def fetch_books(conn, version_id):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT book_id, osis_code, chapter_count
            FROM bible_book
            WHERE version_id=%s
            ORDER BY book_id
        """, (version_id,))
        return cur.fetchall()


def chapter_already_loaded(conn, version_id, book_id, chapter):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM bible_chapter_hash
            WHERE version_id=%s AND book_id=%s AND chapter=%s
            LIMIT 1
        """, (version_id, book_id, chapter))
        return cur.fetchone() is not None

def upsert_verses(conn, rows):
    with conn.cursor() as cur:
        execute_values(cur, UPSERT_VERSE_SQL, rows)

def upsert_chapter_hash(conn, version_id, book_id, chapter, verse_count, h):
    with conn.cursor() as cur:
        cur.execute(
            UPSERT_CHAPTER_HASH_SQL,
            (version_id, book_id, chapter, verse_count, h)
        )

