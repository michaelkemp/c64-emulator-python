import pytest

from c6502.asm.errors import AssemblerError
from c6502.asm.expr import Expr, is_identifier, parse_expr, parse_number


def test_parse_number_hex_binary_decimal():
    assert parse_number("$8000") == 0x8000
    assert parse_number("%1010") == 0b1010
    assert parse_number("128") == 128
    assert parse_number("-5") == -5


def test_parse_number_char_literal():
    assert parse_number("'H'") == ord("H")


def test_parse_number_returns_none_for_non_numbers():
    assert parse_number("label") is None
    assert parse_number("") is None


def test_is_identifier():
    assert is_identifier("start")
    assert is_identifier("_foo123")
    assert not is_identifier("123start")
    assert not is_identifier("$8000")


def test_parse_expr_bare_number():
    expr = parse_expr("$10")
    assert expr == Expr(term="$10", is_label=False, offset=0)
    assert expr.evaluate({}) == 0x10


def test_parse_expr_bare_label():
    expr = parse_expr("start")
    assert expr == Expr(term="start", is_label=True, offset=0)
    assert expr.evaluate({"start": 0x8000}) == 0x8000


def test_parse_expr_label_plus_offset():
    expr = parse_expr("start+2")
    assert expr.evaluate({"start": 0x8000}) == 0x8002


def test_parse_expr_label_minus_offset():
    expr = parse_expr("start-1")
    assert expr.evaluate({"start": 0x8000}) == 0x7FFF


def test_parse_expr_number_minus_offset():
    expr = parse_expr("$8000-5")
    assert expr.evaluate({}) == 0x7FFB


def test_parse_expr_undefined_symbol_raises():
    with pytest.raises(AssemblerError):
        parse_expr("missing").evaluate({})


def test_parse_expr_invalid_raises():
    with pytest.raises(AssemblerError):
        parse_expr("1label")  # not a valid number or identifier


def test_fits_in_byte_literal():
    assert parse_expr("$FF").fits_in_byte_literal
    assert not parse_expr("$100").fits_in_byte_literal
    assert not parse_expr("label").fits_in_byte_literal  # labels never do
