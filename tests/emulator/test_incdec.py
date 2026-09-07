from .helpers import run_at


def test_inc_memory_wraps_and_sets_zero(cpu):
    cpu.bus.write8(0x0010, 0xFF)
    run_at(cpu, 0x0200, 0xE6, 0x10)
    assert cpu.bus.read8(0x0010) == 0x00
    assert cpu.flags.z is True


def test_dec_memory_wraps_and_sets_negative(cpu):
    cpu.bus.write8(0x0010, 0x00)
    run_at(cpu, 0x0200, 0xC6, 0x10)
    assert cpu.bus.read8(0x0010) == 0xFF
    assert cpu.flags.n is True


def test_inx_iny_dex_dey(cpu):
    cpu.x = 0xFF
    run_at(cpu, 0x0200, 0xE8)  # INX
    assert cpu.x == 0x00

    cpu.y = 0x00
    run_at(cpu, 0x0201, 0x88)  # DEY
    assert cpu.y == 0xFF

    cpu.x = 0x01
    run_at(cpu, 0x0202, 0xCA)  # DEX
    assert cpu.x == 0x00

    cpu.y = 0x01
    run_at(cpu, 0x0203, 0xC8)  # INY
    assert cpu.y == 0x02
