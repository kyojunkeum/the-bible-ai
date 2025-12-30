from etl.crawler import build_chapter_url

def test_build_chapter_url_genesis_1():
    url = build_chapter_url("GEN", 1)

    assert "version=HAN" in url
    assert "book=gen" in url
    assert "chap=1" in url
    assert "sec=1" in url

