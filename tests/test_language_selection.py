from api.chat import select_citation_version_id


def test_select_citation_version_id_korean():
    assert select_citation_version_id("en-US", "요즘 불안해요") == "krv"


def test_select_citation_version_id_english():
    assert select_citation_version_id("ko-KR", "I feel anxious today") == "eng-web"


def test_select_citation_version_id_japanese():
    assert select_citation_version_id("ko-KR", "今日は不安です") == "eng-web"


def test_select_citation_version_id_fallback_locale():
    assert select_citation_version_id("ko-KR", "12345") == "krv"
