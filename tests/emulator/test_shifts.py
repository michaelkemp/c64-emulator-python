from .helpers import run_at


def test_asl_accumulator_sets_carry_from_bit7(cpu):
    cpu.a = 0b1000_0001
    run_at(cpu, 0x0200, 0x0A)  # ASL A
    assert cpu.a == 0b0000_0010
    assert cpu.flags.c is True


def test_lsr_memory_sets_carry_from_bit0(cpu):
    cpu.bus.write8(0x0010, 0b0000_0011)
    run_at(cpu, 0x0200, 0x46, 0x10)  # LSR $10
    assert cpu.bus.read8(0x0010) == 0b0000_0001
    assert cpu.flags.c is True


def test_rol_accumulator_rotates_carry_in_and_out(cpu):
    cpu.a = 0b1000_0000
    cpu.flags.c = True
    run_at(cpu, 0x0200, 0x2A)  # ROL A
    assert cpu.a == 0b0000_0001
    assert cpu.flags.c is True  # old bit 7 came out


def test_ror_accumulator_rotates_carry_in_and_out(cpu):
    cpu.a = 0b0000_0001
    cpu.flags.c = True
    run_at(cpu, 0x0200, 0x6A)  # ROR A
    assert cpu.a == 0b1000_0000
    assert cpu.flags.c is True  # old bit 0 came out
    assert cpu.flags.n is True  # carry rotated into bit 7
