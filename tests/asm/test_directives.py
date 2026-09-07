import pytest

from c6502.asm import AssemblerError, assemble


def test_org_sets_origin():
    img = assemble(".org $8000\nNOP")
    assert img.origin == 0x8000
    assert img.data == bytes([0xEA])


def test_byte_numeric_list():
    img = assemble(".org $8000\n.byte $01,$02,3")
    assert img.data == bytes([0x01, 0x02, 0x03])


def test_byte_string_literal():
    img = assemble('.org $8000\n.byte "HI"')
    assert img.data == b"HI"


def test_byte_mixed_string_and_numbers():
    img = assemble('.org $8000\n.byte "HI",0')
    assert img.data == b"HI\x00"


def test_word_numeric_and_label():
    img = assemble(".org $8000\nstart:\nNOP\n.org $FFFC\n.word start")
    # $FFFC/$FFFD hold start's address (0x8000), little-endian
    assert img.data[-2:] == bytes([0x00, 0x80])


def test_word_forward_reference_to_a_later_label():
    img = assemble(".org $8000\n.word later\nlater:\nNOP")
    assert img.data[0:2] == bytes([0x02, 0x80])  # later == $8002 (after the .word)


def test_res_reserves_zero_bytes_and_advances_address():
    img = assemble(".org $8000\n.res 3\nNOP")
    assert img.data == bytes([0x00, 0x00, 0x00, 0xEA])


def test_equate_defines_a_reusable_symbol():
    img = assemble("PORT = $10\n.org $8000\nLDA PORT")
    # An equate is a symbol like a label -- it gets the absolute encoding
    # too, per the "labels always absolute" rule (see test_operands.py's
    # test_absolute_for_any_label_even_if_it_would_fit_zero_page).
    assert img.data == bytes([0xAD, 0x10, 0x00])


def test_duplicate_label_raises():
    with pytest.raises(AssemblerError):
        assemble(".org $8000\nfoo:\nNOP\nfoo:\nNOP")


def test_undefined_symbol_raises():
    with pytest.raises(AssemblerError):
        assemble(".org $8000\nLDA missing")


def test_org_requires_a_literal():
    with pytest.raises(AssemblerError):
        assemble("foo:\n.org foo")


def test_res_requires_a_literal():
    with pytest.raises(AssemblerError):
        assemble("foo:\n.org $8000\n.res foo")


def test_equate_forward_reference_raises():
    with pytest.raises(AssemblerError):
        assemble("PORT = LATER\nLATER = $10\n.org $8000\nNOP")
