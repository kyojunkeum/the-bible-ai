# etl/engweb_crawler.py
import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString

HTML_DIR = Path("etl/eng-web_html")

CHAPTER_STEM_RE = re.compile(r"^(?P<osis>[0-9A-Z]+?)(?P<chapter>\d{1,3})$")
VERSE_ID_RE = re.compile(r"^V(?P<verse>\d+)$")

SKIP_SELECTORS = (
    "ul.tnav",
    "div.footnote",
    "div.copyright",
)


def iter_chapter_files(html_dir: Path = HTML_DIR):
    for path in sorted(html_dir.glob("*.htm")):
        stem = path.stem
        match = CHAPTER_STEM_RE.match(stem)
        if not match:
            continue
        osis_code = match.group("osis")
        chapter = int(match.group("chapter"))
        yield path, osis_code, chapter


def _is_verse_span(tag) -> bool:
    if not getattr(tag, "name", None):
        return False
    if tag.name != "span":
        return False
    if "verse" not in (tag.get("class") or []):
        return False
    verse_id = tag.get("id")
    if not verse_id:
        return False
    return VERSE_ID_RE.match(verse_id) is not None


def _extract_verse_text(verse_span) -> str:
    parts = []
    for sibling in verse_span.next_siblings:
        if _is_verse_span(sibling):
            break
        if isinstance(sibling, NavigableString):
            parts.append(str(sibling))
            continue
        if sibling.name == "a" and "notemark" in (sibling.get("class") or []):
            continue
        parts.append(sibling.get_text(" ", strip=True))

    return " ".join("".join(parts).split())


def parse_chapter_html(html: str):
    soup = BeautifulSoup(html, "html.parser")

    for selector in SKIP_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()

    for tag in soup.select("span.popup, a.notemark"):
        tag.decompose()

    container = soup.select_one("div.main") or soup
    verse_spans = container.select("span.verse[id^=V]")
    if not verse_spans:
        raise ValueError("No verse spans found in chapter HTML.")

    verses = []
    seen = set()
    for verse_span in verse_spans:
        verse_id = verse_span.get("id", "")
        match = VERSE_ID_RE.match(verse_id)
        if not match:
            continue
        verse_no = int(match.group("verse"))
        if verse_no == 0 or verse_no in seen:
            continue
        text = _extract_verse_text(verse_span)
        if text:
            verses.append((verse_no, text))
            seen.add(verse_no)

    if not verses:
        raise ValueError("Verse parsing produced no results.")

    verses.sort(key=lambda x: x[0])
    return verses


def parse_chapter_file(path: Path):
    html = path.read_text(encoding="utf-8-sig")
    return parse_chapter_html(html)
