from .helpers import run_at


def test_and_immediate(cpu):
    cpu.a = 0b1100
    run_at(cpu, 0x0200, 0x29, 0b1010)
    assert cpu.a == 0b1000


def test_ora_immediate(cpu):
    cpu.a = 0b1100
    run_at(cpu, 0x0200, 0x09, 0b0011)
    assert cpu.a == 0b1111


def test_eor_immediate(cpu):
    cpu.a = 0b1100
    run_at(cpu, 0x0200, 0x49, 0b1010)
    assert cpu.a == 0b0110


def test_bit_zero_page_flags_from_memory_not_from_and_result(cpu):
    cpu.a = 0x00
    cpu.bus.write8(0x0010, 0b1100_0000)  # N and V bits set in the operand
    run_at(cpu, 0x0200, 0x24, 0x10)
    assert cpu.flags.z is True  # A & M == 0
    assert cpu.flags.n is True  # bit 7 of M
    assert cpu.flags.v is True  # bit 6 of M
