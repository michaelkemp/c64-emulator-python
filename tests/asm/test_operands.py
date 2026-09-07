import pytest

from c6502.asm.errors import AssemblerError
from c6502.asm.operands import parse_operand


def test_implied_no_operand():
    assert parse_operand("TAX", "") == ("impl", None)


def test_accumulator_bare_and_explicit():
    mode, expr = parse_operand("ASL", "")
    assert mode == "acc" and expr is None
    mode, expr = parse_operand("ASL", "A")
    assert mode == "acc" and expr is None


def test_immediate():
    mode, expr = parse_operand("LDA", "#$05")
    assert mode == "imm"
    assert expr.evaluate({}) == 0x05


def test_immediate_char_literal():
    mode, expr = parse_operand("LDA", "#'H'")
    assert mode == "imm"
    assert expr.evaluate({}) == ord("H")


def test_immediate_rejects_label():
    with pytest.raises(AssemblerError):
        parse_operand("LDA", "#label")


def test_zero_page_for_small_literal():
    mode, _ = parse_operand("LDA", "$10")
    assert mode == "zp"


def test_absolute_for_large_literal():
    mode, _ = parse_operand("LDA", "$1000")
    assert mode == "abs"


def test_absolute_for_any_label_even_if_it_would_fit_zero_page():
    # The deliberate simplification: labels never auto-shrink to zp.
    mode, _ = parse_operand("LDA", "somewhere")
    assert mode == "abs"


def test_zero_page_indexed_x_and_y():
    mode, _ = parse_operand("LDA", "$10,X")
    assert mode == "zpx"
    mode, _ = parse_operand("LDX", "$10,Y")
    assert mode == "zpy"


def test_absolute_indexed_for_large_literal():
    mode, _ = parse_operand("LDA", "$1000,X")
    assert mode == "absx"


def test_indexed_indirect_and_indirect_indexed():
    mode, expr = parse_operand("LDA", "($20,X)")
    assert mode == "indx"
    assert expr.evaluate({}) == 0x20

    mode, expr = parse_operand("LDA", "($20),Y")
    assert mode == "indy"
    assert expr.evaluate({}) == 0x20


def test_jmp_indirect():
    mode, expr = parse_operand("JMP", "($1234)")
    assert mode == "ind"
    assert expr.evaluate({}) == 0x1234


def test_branch_uses_relative_mode():
    mode, _ = parse_operand("BEQ", "target")
    assert mode == "rel"


def test_mnemonic_without_requested_mode_raises():
    with pytest.raises(AssemblerError):
        parse_operand("STX", "$1000,X")  # STX has no absolute,X mode


def test_whitespace_around_indexed_suffix_is_tolerated():
    mode, _ = parse_operand("LDA", "$10, X")
    assert mode == "zpx"
