from etl.utils import chapter_hash

def test_chapter_hash_is_stable():
    verses = [
        (1, "태초에 하나님이 천지를 창조하시니라"),
        (2, "땅이 혼돈하고 공허하며"),
    ]

    h1 = chapter_hash(verses)
    h2 = chapter_hash(verses)

    assert h1 == h2

