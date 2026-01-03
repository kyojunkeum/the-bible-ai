from api.chat import enforce_exact_citations
from api.ref_parser import extract_reference


def test_extract_reference_colon():
    assert extract_reference("창1:1 부탁해요") == ("창", 1, 1, 1)


def test_extract_reference_korean_suffix():
    assert extract_reference("창세기 1장 1절 보여줘") == ("창세기", 1, 1, 1)


def test_extract_reference_osis():
    assert extract_reference("GEN 1:1") == ("GEN", 1, 1, 1)


def test_extract_reference_range():
    assert extract_reference("롬 8:1-2") == ("롬", 8, 1, 2)


def test_extract_reference_compact():
    assert extract_reference("고전13:4") == ("고전", 13, 4, 4)


def test_extract_reference_none():
    assert extract_reference("그냥 인사") is None


def test_enforce_exact_citations_replaces_wrong_text():
    citations = [
        {
            "version_id": "krv",
            "book_id": 1,
            "book_name": "창세기",
            "chapter": 1,
            "verse_start": 1,
            "verse_end": 1,
            "text": "태초에 하나님이 천지를 창조하시니라",
        }
    ]
    response = "(창세기 1:1) 틀린본문"
    new_response, new_citations = enforce_exact_citations(response, citations)

    assert "틀린본문" not in new_response
    assert "태초에 하나님이 천지를 창조하시니라" in new_response
    assert new_citations == citations


def test_enforce_exact_citations_appends_when_missing():
    citations = [
        {
            "version_id": "krv",
            "book_id": 1,
            "book_name": "창세기",
            "chapter": 1,
            "verse_start": 1,
            "verse_end": 1,
            "text": "태초에 하나님이 천지를 창조하시니라",
        }
    ]
    response = "테스트 응답"
    new_response, _ = enforce_exact_citations(response, citations)
    assert "테스트 응답" in new_response
    assert "태초에 하나님이 천지를 창조하시니라" in new_response


def test_append_range_formatting():
    from api.chat import append_citations_to_response

    citations = [
        {
            "version_id": "krv",
            "book_id": 45,
            "book_name": "로마서",
            "chapter": 8,
            "verse_start": 1,
            "verse_end": 2,
            "text": "내용",
        }
    ]
    response = append_citations_to_response("", citations)
    assert "(로마서 8:1-2) 내용" in response
