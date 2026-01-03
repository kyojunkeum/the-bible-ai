import pytest
from api.ref_parser import parse_reference


def test_parse_reference_with_explicit_params():
    book, ch, vs = parse_reference("창세기", 1, 1)
    assert book == "창세기"
    assert ch == 1
    assert vs == 1


def test_parse_reference_compact_colon():
    book, ch, vs = parse_reference("창1:1", None, None)
    assert book == "창"
    assert ch == 1
    assert vs == 1


def test_parse_reference_korean_suffix():
    book, ch, vs = parse_reference("창세기 1장 1절", None, None)
    assert book == "창세기"
    assert ch == 1
    assert vs == 1


def test_parse_reference_osis():
    book, ch, vs = parse_reference("GEN 1:1", None, None)
    assert book == "GEN"
    assert ch == 1
    assert vs == 1


def test_parse_reference_invalid():
    with pytest.raises(ValueError):
        parse_reference("창세기", None, None)
