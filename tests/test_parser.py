from bs4 import BeautifulSoup
from etl.crawler import parse_verses


def _normalize_ws(s: str) -> str:
    """공백만 정규화 (의미 변경 없음)"""
    return " ".join((s or "").split())


def _expected_from_html(html: str):
    """
    fixtures HTML에서 '절 번호(span.number)만 제거'한 뒤
    각 절(span)의 남은 텍스트를 기대값으로 생성한다.
    parse_verses()가 '모든 텍스트를 그대로' 잡았는지 비교하기 위함.
    """
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one("div#tdBible1.bible_read")
    if not container:
        raise AssertionError("fixtures에 #tdBible1.bible_read가 없습니다.")

    expected = []

    # 절 단위 span (직계)
    for span in container.find_all("span", recursive=False):
        num_tag = span.select_one("span.number")
        if not num_tag:
            continue

        # 절 번호
        verse_no_text = num_tag.get_text(strip=True)
        try:
            verse_no = int(verse_no_text)
        except ValueError:
            continue

        # 깊은 복사 대신: 이 테스트는 fixtures 파싱만 하므로 안전하게 extract
        num_tag.extract()

        text = span.get_text(" ", strip=True)
        text = _normalize_ws(text)

        expected.append((verse_no, text))

    if not expected:
        raise AssertionError("fixtures에서 기대 절 목록을 만들지 못했습니다.")

    return expected


def test_parse_exodus_2_captures_all_text():
    """
    '모든 텍스트를 빠짐없이 잡았는지' 강력 검증:
    fixtures HTML에서 계산한 기대값과 parse_verses 결과가 1:1 동일해야 한다.
    """
    with open("tests/fixtures/exo_2.html", encoding="utf-8") as f:
        html = f.read()

    expected = _expected_from_html(html)
    got = [(v, _normalize_ws(t)) for v, t in parse_verses(html)]

    # 1) 절 개수 동일
    assert len(got) == len(expected)

    # 2) 절 번호 시퀀스 동일
    assert [v for v, _ in got] == [v for v, _ in expected]

    # 3) 절 본문 텍스트가 완전히 동일해야 함 (공백만 정규화)
    #    실패 시 어느 절에서 누락/추가가 났는지 바로 알 수 있게 메시지 제공
    for (v1, t1), (v2, t2) in zip(got, expected):
        print(f"[VERSE {v1}] {t1}")
        assert v1 == v2
        assert t1 == t2, f"verse {v1} mismatch\nGOT: {t1}\nEXP: {t2}"