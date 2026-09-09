"""Tests for the implemented subset of undocumented/"illegal" 6502
opcodes -- see opcodes.py's and instructions.py's "illegal/undocumented
opcodes" sections, and docs/6502-reference.md for citations.

Addressing-mode mechanics (page-crossing, zero-page wraparound, etc.) are
already covered exhaustively by the legal-opcode tests in this directory
-- these illegal opcodes reuse the same addressing.py functions, so each
gets one or two representative tests focused on its own instruction
semantics, not repeated addressing-mode coverage.
"""

import pytest

from c6502.emulator.cpu import IllegalOpcodeError, ProcessorJammed

from .helpers import run_at


def test_lax_loads_a_and_x_together(cpu):
    cpu.bus.write8(0x0010, 0x42)
    run_at(cpu, 0x0200, 0xA7, 0x10)  # LAX zp
    assert cpu.a == 0x42
    assert cpu.x == 0x42
    assert cpu.flags.z is False
    assert cpu.flags.n is False


def test_sax_stores_a_and_x_without_touching_flags(cpu):
    cpu.a = 0xF0
    cpu.x = 0x3C
    cpu.flags.z = True  # deliberately "wrong" beforehand -- SAX must not touch it
    run_at(cpu, 0x0200, 0x87, 0x10)  # SAX zp
    assert cpu.bus.read8(0x0010) == 0x30
    assert cpu.flags.z is True


def test_dcp_decrements_then_compares(cpu):
    cpu.bus.write8(0x0010, 0x11)
    cpu.a = 0x10
    run_at(cpu, 0x0200, 0xC7, 0x10)  # DCP zp
    assert cpu.bus.read8(0x0010) == 0x10
    assert cpu.flags.z is True
    assert cpu.flags.c is True


def test_isc_increments_then_subtracts(cpu):
    cpu.bus.write8(0x0010, 0x05)
    cpu.a = 0x10
    cpu.flags.c = True  # no incoming borrow
    run_at(cpu, 0x0200, 0xE7, 0x10)  # ISC zp
    assert cpu.bus.read8(0x0010) == 0x06
    assert cpu.a == 0x0A
    assert cpu.flags.c is True  # no borrow occurred


def test_slo_shifts_then_ors(cpu):
    cpu.bus.write8(0x0010, 0x81)
    cpu.a = 0x02
    run_at(cpu, 0x0200, 0x07, 0x10)  # SLO zp
    assert cpu.bus.read8(0x0010) == 0x02
    assert cpu.a == 0x02
    assert cpu.flags.c is True  # bit 7 of the original value


def test_rla_rotates_then_ands(cpu):
    cpu.bus.write8(0x0010, 0x80)
    cpu.a = 0xFF
    cpu.flags.c = True
    run_at(cpu, 0x0200, 0x27, 0x10)  # RLA zp
    assert cpu.bus.read8(0x0010) == 0x01
    assert cpu.a == 0x01
    assert cpu.flags.c is True  # bit 7 of the original value


def test_sre_shifts_then_eors(cpu):
    cpu.bus.write8(0x0010, 0x03)
    cpu.a = 0x0C
    run_at(cpu, 0x0200, 0x47, 0x10)  # SRE zp
    assert cpu.bus.read8(0x0010) == 0x01
    assert cpu.a == 0x0D
    assert cpu.flags.c is True  # bit 0 of the original value


def test_rra_chains_ror_carry_into_the_adc(cpu):
    """The ROR's carry-out must feed the ADC's carry-in -- if RRA instead
    reused the *old* carry, the sum below would be $10, not $11."""
    cpu.bus.write8(0x0010, 0x01)
    cpu.a = 0x10
    cpu.flags.c = False
    run_at(cpu, 0x0200, 0x67, 0x10)  # RRA zp
    assert cpu.bus.read8(0x0010) == 0x00
    assert cpu.a == 0x11
    assert cpu.flags.c is False  # from the ADC, overwriting the ROR's carry


def test_anc_sets_carry_from_result_sign_bit(cpu):
    cpu.a = 0xF0
    run_at(cpu, 0x0200, 0x0B, 0x81)  # ANC #$81
    assert cpu.a == 0x80
    assert cpu.flags.n is True
    assert cpu.flags.c is True

    # $2B is the same operation under a second opcode byte.
    cpu.a = 0xF0
    run_at(cpu, 0x0202, 0x2B, 0x81)  # ANC #$81
    assert cpu.a == 0x80
    assert cpu.flags.c is True


def test_alr_ands_then_shifts_right(cpu):
    cpu.a = 0x03
    run_at(cpu, 0x0200, 0x4B, 0x03)  # ALR #$03
    assert cpu.a == 0x01
    assert cpu.flags.c is True  # bit 0 of (A AND operand)


def test_arr_ands_then_rotates_with_bit6_bit5_flags(cpu):
    cpu.a = 0xC0
    cpu.flags.c = False
    run_at(cpu, 0x0200, 0x6B, 0xC0)  # ARR #$C0
    assert cpu.a == 0x60
    assert cpu.flags.c is True   # bit 6 of the result
    assert cpu.flags.v is False  # bit 6 XOR bit 5 of the result


def test_sbx_combines_and_and_compare_into_x(cpu):
    cpu.a = 0xFF
    cpu.x = 0xFF
    run_at(cpu, 0x0200, 0xCB, 0x0F)  # SBX #$0F
    assert cpu.x == 0xF0
    assert cpu.flags.c is True  # (A AND X) >= operand, no borrow


def test_usbc_behaves_exactly_like_legal_sbc(cpu):
    cpu.a = 0x10
    cpu.flags.c = True  # no incoming borrow
    run_at(cpu, 0x0200, 0xEB, 0x05)  # USBC #$05 ($EB)
    assert cpu.a == 0x0B
    assert cpu.flags.c is True


@pytest.mark.parametrize(
    "opcode_bytes,expected_pc_advance,expected_cycles",
    [
        ((0x1A,), 1, 2),   # implied, 1-byte multi-cycle NOP
        ((0x80, 0x00), 2, 2),  # immediate
        ((0x04, 0x00), 2, 3),  # zeropage
        ((0x14, 0x00), 2, 4),  # zeropage,X
        ((0x0C, 0x00, 0x00), 3, 4),  # absolute
    ],
)
def test_illegal_nops_consume_operand_and_advance_pc(
    cpu, opcode_bytes, expected_pc_advance, expected_cycles
):
    cpu.a, cpu.x, cpu.y = 0x11, 0x22, 0x33
    result = run_at(cpu, 0x0200, *opcode_bytes)
    assert cpu.pc == 0x0200 + expected_pc_advance
    assert result.cycles == expected_cycles
    assert (cpu.a, cpu.x, cpu.y) == (0x11, 0x22, 0x33)


def test_illegal_nop_absolute_x_page_cross_adds_cycle(cpu):
    cpu.x = 0x01
    result = run_at(cpu, 0x0200, 0x1C, 0xFF, 0x12)  # NOP $12FF,X -> crosses to $1300
    assert result.cycles == 5


def test_illegal_nop_absolute_x_no_page_cross_cycles(cpu):
    cpu.x = 0x01
    result = run_at(cpu, 0x0200, 0x1C, 0x34, 0x12)  # NOP $1234,X -> no cross
    assert result.cycles == 4


@pytest.mark.parametrize(
    "jam_opcode",
    [0x02, 0x12, 0x22, 0x32, 0x42, 0x52, 0x62, 0x72, 0x92, 0xB2, 0xD2, 0xF2],
)
def test_jam_opcodes_raise_processor_jammed(cpu, jam_opcode):
    cpu.bus.write8(0x0200, jam_opcode)
    cpu.pc = 0x0200
    with pytest.raises(ProcessorJammed) as excinfo:
        cpu.step()
    assert excinfo.value.opcode == jam_opcode
    assert excinfo.value.pc == 0x0200


@pytest.mark.parametrize(
    "unstable_opcode",
    [0x8B, 0xAB, 0xBB, 0x9F, 0x93, 0x9E, 0x9C, 0x9B],
)
def test_chip_unstable_opcodes_still_raise_illegal_opcode_error(cpu, unstable_opcode):
    """ANE/XAA, LXA, LAS, SHA, SHX, SHY, TAS: deliberately not implemented
    (see docs/6502-reference.md) -- confirms they weren't accidentally
    swept up while adding the reliable illegal opcodes above."""
    cpu.bus.write8(0x0200, unstable_opcode)
    cpu.pc = 0x0200
    with pytest.raises(IllegalOpcodeError):
        cpu.step()
