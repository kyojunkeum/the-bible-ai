# etl/crawler.py
import requests
from bs4 import BeautifulSoup, NavigableString
from tenacity import retry, stop_after_attempt, wait_exponential
from etl.config import USER_AGENT, RAW_HTML_DIR
from etl.utils import ensure_dir

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "ko-KR,ko;q=0.9",
}

def build_chapter_url(book_osis: str, chapter: int) -> str:
    """
    대한성서공회 개역한글(KRV) 장 단위 URL
    sec=1은 포커스용이므로 고정
    """
    book = book_osis.lower()

    return (
        "https://www.bskorea.or.kr/bible/korbibReadpage.php"
        f"?version=HAN&book={book}&chap={chapter}&sec=1"
    )

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
def fetch_chapter_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text

def parse_verses(html: str):
    """
    최종 안정판 파서

    원칙:
    - 절의 시작은 span.number
    - 각 span.number의 '바로 위 부모 span'을 절 컨테이너로 본다
    - 원본 DOM을 훼손하지 않기 위해 '절 컨테이너 HTML을 복사'해서 number만 제거 후 텍스트 추출
    - 숨김 주석(div.D2)은 제거
    """

    soup = BeautifulSoup(html, "html.parser")

    container = soup.select_one("div#tdBible1.bible_read")
    if not container:
        raise ValueError("본문 컨테이너(#tdBible1.bible_read)를 찾지 못했습니다.")

    # 숨김 주석 제거(팝업 주석)
    for d in container.select("div.D2"):
        d.decompose()

    num_tags = container.select("span.number")
    if not num_tags:
        # 차단/오류/구조변경 페이지일 수 있음
        raise ValueError("span.number를 찾지 못했습니다. (차단/오류/DOM 변경 가능)")

    verses = []
    seen = set()

    for num_tag in num_tags:
        num_text = num_tag.get_text(strip=True)
        try:
            verse_no = int(num_text)
        except ValueError:
            continue

        # span.number를 감싸는 절 컨테이너 span
        verse_span = num_tag.find_parent("span")
        if verse_span is None:
            continue

        # ✅ 원본 훼손 금지: 복사본에서 number 제거 후 텍스트 추출
        tmp = BeautifulSoup(str(verse_span), "html.parser")

        # number 제거
        for n in tmp.select("span.number"):
            n.decompose()

        # 혹시 절 안에 숨김 주석이 또 섞이면 제거
        for d in tmp.select("div.D2"):
            d.decompose()

        text = tmp.get_text(" ", strip=True)
        text = " ".join(text.split())  # 공백만 정리

        if text and (verse_no not in seen):
            verses.append((verse_no, text))
            seen.add(verse_no)

    if not verses:
        raise ValueError("절 파싱 결과가 비어 있습니다.")

    verses.sort(key=lambda x: x[0])
    return verses


def save_raw_html(book_id, chapter, html):
    ensure_dir(RAW_HTML_DIR)
    path = f"{RAW_HTML_DIR}/book{book_id}_ch{chapter}.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

