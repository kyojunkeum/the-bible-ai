import os

import pytest
import psycopg2

from api.config import DB
from api.search import search_verses


def _get_conn():
    return psycopg2.connect(**DB)


def _db_ready(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.bible_verse')")
        if cur.fetchone()[0] is None:
            return False
        cur.execute("SELECT COUNT(*) FROM bible_verse")
        return cur.fetchone()[0] > 0


@pytest.mark.skipif(os.getenv("BIBLE_DB_TEST") != "1", reason="BIBLE_DB_TEST not enabled")
def test_search_verses_db_integration():
    with _get_conn() as conn:
        if not _db_ready(conn):
            pytest.skip("Bible data not loaded")
        result = search_verses(conn, "krv", "태초", 5, 0)
        assert "total" in result
        assert "items" in result
        assert isinstance(result["items"], list)

