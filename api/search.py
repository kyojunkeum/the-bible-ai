from typing import Dict, List
from psycopg2.extras import RealDictCursor
from etl.utils import normalize_text


TRGM_SIMILARITY_THRESHOLD = 0.3


def _vector_literal(values: List[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


def search_verses(conn, version_id: str, query: str, limit: int, offset: int) -> Dict[str, List[dict]]:
    normalized_query = normalize_text(query or "")
    if not normalized_query:
        return {"total": 0, "items": []}

    use_tsquery = len(normalized_query) >= 2
    ts_query = normalized_query
    like_pattern = f"%{normalized_query}%"

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS total
            FROM bible_verse v
            WHERE v.version_id = %s
              AND (
                (%s AND v.search_vector @@ plainto_tsquery('simple', %s))
                OR v.normalized ILIKE %s
                OR similarity(v.normalized, %s) > %s
              )
            """,
            (version_id, use_tsquery, ts_query, like_pattern, normalized_query, TRGM_SIMILARITY_THRESHOLD),
        )
        total = cur.fetchone()["total"]

        cur.execute(
            """
            SELECT
                v.book_id,
                b.ko_name AS book_name,
                v.chapter,
                v.verse,
                ts_headline(
                    'simple',
                    v.text,
                    plainto_tsquery('simple', %s),
                    'StartSel=<b>, StopSel=</b>, MaxWords=24, MinWords=8, ShortWord=2, HighlightAll=true'
                ) AS snippet,
                v.text,
                CASE WHEN v.text ILIKE %s THEN 1 ELSE 0 END AS exact_rank,
                CASE WHEN v.search_vector @@ plainto_tsquery('simple', %s) THEN 0 ELSE 1 END AS fallback_rank,
                ts_rank_cd(v.search_vector, plainto_tsquery('simple', %s)) AS rank,
                similarity(v.normalized, %s) AS trgm_sim
            FROM bible_verse v
            JOIN bible_book b
              ON b.version_id = v.version_id AND b.book_id = v.book_id
            WHERE v.version_id = %s
              AND (
                (%s AND v.search_vector @@ plainto_tsquery('simple', %s))
                OR v.normalized ILIKE %s
                OR similarity(v.normalized, %s) > %s
              )
            ORDER BY exact_rank DESC, fallback_rank ASC, rank DESC, trgm_sim DESC, v.book_id, v.chapter, v.verse
            LIMIT %s OFFSET %s
            """,
            (
                ts_query,
                like_pattern,
                ts_query,
                ts_query,
                normalized_query,
                version_id,
                use_tsquery,
                ts_query,
                like_pattern,
                normalized_query,
                TRGM_SIMILARITY_THRESHOLD,
                limit,
                offset,
            ),
        )
        rows = cur.fetchall()

    items = [
        {
            "book_id": row["book_id"],
            "book_name": row["book_name"],
            "chapter": row["chapter"],
            "verse": row["verse"],
            "snippet": row["snippet"] or row["text"],
            "text": row["text"],
            "rank": row["rank"],
            "trgm_sim": row["trgm_sim"],
        }
        for row in rows
    ]

    return {"total": total, "items": items}


def search_verses_vector(
    conn,
    version_id: str,
    embedding: List[float],
    limit: int,
    window_size: int,
) -> List[dict]:
    if not embedding:
        return []
    vector = _vector_literal(embedding)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    v.book_id,
                    b.ko_name AS book_name,
                    v.chapter,
                    v.verse,
                    v.text,
                    w.distance
                FROM (
                    SELECT
                        book_id,
                        chapter,
                        verse_start,
                        verse_end,
                        embedding <-> %s::vector AS distance
                    FROM bible_verse_window
                    WHERE version_id = %s
                      AND (verse_end - verse_start + 1) = %s
                      AND embedding IS NOT NULL
                    ORDER BY embedding <-> %s::vector
                    LIMIT %s
                ) AS w
                JOIN bible_verse v
                  ON v.version_id = %s
                 AND v.book_id = w.book_id
                 AND v.chapter = w.chapter
                 AND v.verse BETWEEN w.verse_start AND w.verse_end
                JOIN bible_book b
                  ON b.version_id = v.version_id
                 AND b.book_id = v.book_id
                ORDER BY w.distance ASC, v.verse ASC
                """,
                (
                    vector,
                    version_id,
                    window_size,
                    vector,
                    limit,
                    version_id,
                ),
            )
            rows = cur.fetchall()
    except Exception:
        return []

    return [
        {
            "book_id": row["book_id"],
            "book_name": row["book_name"],
            "chapter": row["chapter"],
            "verse": row["verse"],
            "text": row["text"],
            "vector_distance": row["distance"],
            "source": "vector",
        }
        for row in rows
    ]
