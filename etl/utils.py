# etl/utils.py
import re
import hashlib
import time
import os

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def normalize_text(s: str) -> str:
    # ⚠️ 크롤링 도중 변경 금지
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    # 구두점 공백화(검색 품질 ↑)
    s = re.sub(r"[,:;.!?\"'()\[\]{}]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def chapter_hash(verses):
    """
    verses: list of (verse_no:int, text:str)
    """
    joined = "|".join(f"{v}:{t}" for v, t in verses)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()

def sleep_delay(sec: float):
    time.sleep(sec)

