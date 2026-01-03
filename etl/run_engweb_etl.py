# etl/run_engweb_etl.py
from etl.config import DB
from etl.utils import normalize_text, chapter_hash
from etl.db import (
    get_conn,
    fetch_books,
    chapter_already_loaded,
    upsert_verses,
    upsert_chapter_hash,
)
from etl.engweb_crawler import iter_chapter_files, parse_chapter_file

VERSION_ID = "eng-web"
SOURCE_VERSION_ID = "krv"

VERSION_NAME = "World English Bible Classic (Public Domain)"
VERSION_PUBLISHER = "eBible.org"
VERSION_COPYRIGHT = "Public domain. Source: eBible.org (World English Bible Classic)."

OSIS_ALIASES = {
    "JON": "JNH",
}


def ensure_version_and_books(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bible_version
            (version_id, name, publisher, copyright_notice)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (version_id) DO NOTHING
            """,
            (VERSION_ID, VERSION_NAME, VERSION_PUBLISHER, VERSION_COPYRIGHT),
        )

        cur.execute(
            """
            INSERT INTO bible_book
            (version_id, book_id, osis_code, ko_name, abbr, chapter_count, testament)
            SELECT %s, book_id, osis_code, ko_name, abbr, chapter_count, testament
            FROM bible_book
            WHERE version_id = %s
            ON CONFLICT (version_id, book_id) DO NOTHING
            """,
            (VERSION_ID, SOURCE_VERSION_ID),
        )


def main():
    conn = get_conn(DB)
    conn.autocommit = False

    try:
        ensure_version_and_books(conn)
        conn.commit()

        books = fetch_books(conn, VERSION_ID)
        book_map = {
            osis_code.upper(): (book_id, chapter_count)
            for book_id, osis_code, chapter_count in books
        }

        for path, osis_code, chapter in iter_chapter_files():
            lookup_code = OSIS_ALIASES.get(osis_code, osis_code)
            book_meta = book_map.get(lookup_code)
            if not book_meta:
                continue
            if chapter == 0:
                continue
            book_id, chapter_count = book_meta
            if chapter > chapter_count:
                print(
                    f"WARN skip chapter out of range book={book_id}({osis_code}) ch={chapter}",
                    flush=True,
                )
                continue

            if chapter_already_loaded(conn, VERSION_ID, book_id, chapter):
                print(f"SKIP book={book_id} ch={chapter}")
                continue

            try:
                verses = parse_chapter_file(path)
            except ValueError as exc:
                print(
                    f"WARN parse failed book={book_id}({osis_code}) ch={chapter} file={path} err={exc}",
                    flush=True,
                )
                conn.rollback()
                continue

            rows = []
            for verse_no, text in verses:
                rows.append(
                    (
                        VERSION_ID,
                        book_id,
                        chapter,
                        verse_no,
                        text,
                        normalize_text(text),
                    )
                )

            upsert_verses(conn, rows)

            h = chapter_hash(verses)
            upsert_chapter_hash(
                conn,
                VERSION_ID,
                book_id,
                chapter,
                len(verses),
                h,
            )

            conn.commit()
            print(
                f"OK book={book_id}({osis_code}) "
                f"ch={chapter} verses={len(verses)}"
            )

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
