import re
from typing import Optional, Tuple


def parse_reference(book: str, chapter: Optional[int], verse: Optional[int]) -> Tuple[str, int, int]:
    if chapter is not None and verse is not None:
        return book.strip(), int(chapter), int(verse)

    raw = (book or "").strip()
    compact = re.sub(r"\s+", "", raw)

    patterns = [
        r"^(?P<book>.+?)(?P<chapter>\d+):(?P<verse>\d+)$",
        r"^(?P<book>.+?)(?P<chapter>\d+)장(?P<verse>\d+)절?$",
        r"^(?P<book>.+?)(?P<chapter>\d+)(?P<verse>\d+)$",
    ]

    for pat in patterns:
        m = re.match(pat, compact)
        if not m:
            continue
        book_name = m.group("book")
        ch = int(m.group("chapter"))
        vs = int(m.group("verse"))
        return book_name, ch, vs

    raise ValueError("invalid reference")


def extract_reference(text: str) -> Optional[Tuple[str, int, int, int]]:
    if not text:
        return None

    patterns = [
        r"(?P<book>(?:[1-3]\s*)?[A-Za-z가-힣]+)\s*(?P<chapter>\d+)\s*:\s*(?P<verse>\d+)(?:\s*[-~]\s*(?P<verse_end>\d+))?",
        r"(?P<book>(?:[1-3]\s*)?[A-Za-z가-힣]+)\s*(?P<chapter>\d+)\s*장\s*(?P<verse>\d+)\s*절?(?:\s*[-~]\s*(?P<verse_end>\d+)\s*절?)?",
    ]

    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if not m:
            continue
        book_name = re.sub(r"\s+", "", m.group("book")).strip(".,")
        ch = int(m.group("chapter"))
        vs = int(m.group("verse"))
        vs_end = int(m.group("verse_end")) if m.group("verse_end") else vs
        if vs_end < vs:
            vs_end = vs
        return book_name, ch, vs, vs_end

    return None
