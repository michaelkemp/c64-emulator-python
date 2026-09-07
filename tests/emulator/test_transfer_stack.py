from .helpers import run_at


def test_tax_tay_copy_accumulator_and_set_flags(cpu):
    cpu.a = 0x80
    run_at(cpu, 0x0200, 0xAA)  # TAX
    assert cpu.x == 0x80
    assert cpu.flags.n is True

    cpu.a = 0x00
    run_at(cpu, 0x0202, 0xA8)  # TAY
    assert cpu.y == 0x00
    assert cpu.flags.z is True


def test_txa_tya(cpu):
    cpu.x = 0x11
    run_at(cpu, 0x0200, 0x8A)  # TXA
    assert cpu.a == 0x11

    cpu.y = 0x22
    run_at(cpu, 0x0202, 0x98)  # TYA
    assert cpu.a == 0x22


def test_tsx_reads_stack_pointer(cpu):
    cpu.sp = 0x42
    run_at(cpu, 0x0200, 0xBA)  # TSX
    assert cpu.x == 0x42


def test_txs_does_not_touch_flags(cpu):
    cpu.x = 0x00
    cpu.flags.z = False
    run_at(cpu, 0x0200, 0x9A)  # TXS
    assert cpu.sp == 0x00
    assert cpu.flags.z is False  # TXS must not set Z despite X being zero


def test_pha_pla_round_trip(cpu):
    cpu.a = 0x37
    run_at(cpu, 0x0200, 0x48)  # PHA
    cpu.a = 0x00
    run_at(cpu, 0x0201, 0x68)  # PLA
    assert cpu.a == 0x37


def test_php_sets_break_bit_plp_restores_flags(cpu):
    cpu.flags.c = True
    cpu.flags.n = True
    run_at(cpu, 0x0200, 0x08)  # PHP
    pushed = cpu.bus.read8(0x0100 + cpu.sp + 1)
    assert pushed & 0x10  # break bit set on a PHP push
    assert pushed & 0x20  # unused bit always set

    cpu.flags.c = False
    cpu.flags.n = False
    run_at(cpu, 0x0201, 0x28)  # PLP
    assert cpu.flags.c is True
    assert cpu.flags.n is True
