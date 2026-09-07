import pytest

from c6502.asm import AssemblerError, assemble


def test_backward_branch():
    src = """
    .org $8000
loop:
    NOP
    BNE loop
"""
    img = assemble(src)
    # NOP ($EA), then BNE loop: opcode $D0, offset = loop - (branch_addr+2)
    # loop = $8000, branch instruction at $8001, next-instr addr = $8003
    # offset = 0x8000 - 0x8003 = -3
    assert img.data == bytes([0xEA, 0xD0, (-3) & 0xFF])


def test_forward_branch():
    src = """
    .org $8000
    BEQ done
    NOP
done:
    NOP
"""
    img = assemble(src)
    # BEQ done: opcode $F0 at $8000, next-instr addr $8002, done=$8003
    # offset = 0x8003 - 0x8002 = 1
    assert img.data[0:2] == bytes([0xF0, 0x01])


def test_out_of_range_branch_raises():
    lines = [".org $8000", "target:", "NOP"]
    lines += [f"NOP" for _ in range(200)]  # push the branch out of +/-127 range
    lines.append("BEQ target")
    with pytest.raises(AssemblerError):
        assemble("\n".join(lines))


def test_jmp_to_forward_label_always_absolute_even_if_small_address():
    # start is at $0010 -- would fit zero page, but JMP has no zero-page
    # mode anyway, so this just proves labels resolve correctly for JMP.
    img = assemble(".org $0010\nstart:\nJMP start")
    assert img.data == bytes([0x4C, 0x10, 0x00])


def test_lda_label_is_absolute_even_when_address_fits_zero_page():
    # The deliberate simplification: a *label* never gets the zero-page
    # encoding, even though $0010 would fit -- only a bare literal does.
    src = ".org $0010\nvalue:\nNOP\n.org $8000\nLDA value"
    img = assemble(src)
    assert img.data[-3:] == bytes([0xAD, 0x10, 0x00])  # LDA abs, not $A5 zp
