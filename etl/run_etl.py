# etl/run_etl.py
from etl.config import DB, VERSION_ID, REQUEST_DELAY_SEC
from etl.utils import normalize_text, chapter_hash, sleep_delay
from etl.db import (
    get_conn, fetch_books, chapter_already_loaded,
    upsert_verses, upsert_chapter_hash
)
from etl.crawler import (
    build_chapter_url, fetch_chapter_html,
    parse_verses, save_raw_html
)

def main():
    conn = get_conn(DB)
    conn.autocommit = False

    try:
        # book_id, osis_code, chapter_count
        books = fetch_books(conn, VERSION_ID)

        for book_id, osis_code, chapter_count in books:
            for chapter in range(1, chapter_count + 1):

                if chapter_already_loaded(conn, VERSION_ID, book_id, chapter):
                    print(f"SKIP book={book_id} ch={chapter}")
                    continue

                # 🔑 osis_code 기반 URL 생성
                url = build_chapter_url(osis_code, chapter)

                html = fetch_chapter_html(url)
                save_raw_html(book_id, chapter, html)

                try:
                    verses = parse_verses(html)
                except ValueError as e:
                    print(
                        f"WARN parse failed book={book_id}({osis_code}) ch={chapter} url={url} err={e}",
                        flush=True
                    )
                    conn.rollback()
                    continue  
                
                rows = []
                for verse_no, text in verses:
                    rows.append((
                        VERSION_ID,
                        book_id,
                        chapter,
                        verse_no,
                        text,
                        normalize_text(text),
                    ))

                upsert_verses(conn, rows)

                h = chapter_hash(verses)
                upsert_chapter_hash(
                    conn,
                    VERSION_ID,
                    book_id,
                    chapter,
                    len(verses),
                    h
                )

                conn.commit()
                print(
                    f"OK book={book_id}({osis_code}) "
                    f"ch={chapter} verses={len(verses)}"
                )

                sleep_delay(REQUEST_DELAY_SEC)

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
