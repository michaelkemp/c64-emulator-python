from .helpers import run_at


def test_cmp_equal_sets_zero_and_carry(cpu):
    cpu.a = 0x10
    run_at(cpu, 0x0200, 0xC9, 0x10)
    assert cpu.flags.z is True
    assert cpu.flags.c is True
    assert cpu.flags.n is False


def test_cmp_accumulator_greater_sets_carry_only(cpu):
    cpu.a = 0x20
    run_at(cpu, 0x0200, 0xC9, 0x10)
    assert cpu.flags.z is False
    assert cpu.flags.c is True


def test_cmp_accumulator_less_clears_carry(cpu):
    cpu.a = 0x05
    run_at(cpu, 0x0200, 0xC9, 0x10)
    assert cpu.flags.c is False
    assert cpu.flags.n is True  # 0x05 - 0x10 == 0xF5, bit 7 set


def test_cpx_and_cpy(cpu):
    cpu.x = 0x03
    run_at(cpu, 0x0200, 0xE0, 0x03)
    assert cpu.flags.z is True

    cpu.y = 0x01
    run_at(cpu, 0x0202, 0xC0, 0x02)
    assert cpu.flags.c is False
