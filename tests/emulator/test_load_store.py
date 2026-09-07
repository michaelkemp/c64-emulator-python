from .helpers import run_at


def test_lda_immediate_sets_value_and_flags(cpu):
    run_at(cpu, 0x0200, 0xA9, 0x05)
    assert cpu.a == 0x05
    assert cpu.flags.z is False
    assert cpu.flags.n is False


def test_lda_immediate_zero_sets_zero_flag(cpu):
    run_at(cpu, 0x0200, 0xA9, 0x00)
    assert cpu.flags.z is True


def test_lda_immediate_negative_sets_negative_flag(cpu):
    run_at(cpu, 0x0200, 0xA9, 0x80)
    assert cpu.flags.n is True


def test_lda_zero_page(cpu):
    cpu.bus.write8(0x0010, 0x42)
    run_at(cpu, 0x0200, 0xA5, 0x10)
    assert cpu.a == 0x42


def test_lda_zero_page_x_wraps(cpu):
    cpu.x = 0xFF
    cpu.bus.write8(0x0004, 0x99)  # (0x05 + 0xFF) & 0xFF == 0x04
    run_at(cpu, 0x0200, 0xB5, 0x05)
    assert cpu.a == 0x99


def test_lda_absolute(cpu):
    cpu.bus.write8(0x1234, 0x77)
    run_at(cpu, 0x0200, 0xAD, 0x34, 0x12)
    assert cpu.a == 0x77


def test_lda_absolute_x_no_page_cross_cycles(cpu):
    cpu.x = 0x01
    cpu.bus.write8(0x1235, 0x01)
    result = run_at(cpu, 0x0200, 0xBD, 0x34, 0x12)
    assert cpu.a == 0x01
    assert result.cycles == 4


def test_lda_absolute_x_page_cross_adds_cycle(cpu):
    cpu.x = 0x01
    cpu.bus.write8(0x1300, 0x02)  # 0x12FF + 1 crosses into $1300
    result = run_at(cpu, 0x0200, 0xBD, 0xFF, 0x12)
    assert cpu.a == 0x02
    assert result.cycles == 5


def test_lda_indexed_indirect(cpu):
    cpu.x = 0x04
    cpu.bus.write16(0x0024, 0x0300)  # ($20 + X) -> pointer at $0300
    cpu.bus.write8(0x0300, 0x55)
    run_at(cpu, 0x0200, 0xA1, 0x20)
    assert cpu.a == 0x55


def test_lda_indirect_indexed(cpu):
    cpu.y = 0x10
    cpu.bus.write16(0x0020, 0x0300)
    cpu.bus.write8(0x0310, 0x66)
    run_at(cpu, 0x0200, 0xB1, 0x20)
    assert cpu.a == 0x66


def test_ldx_and_ldy_basic(cpu):
    run_at(cpu, 0x0200, 0xA2, 0x07)
    assert cpu.x == 0x07
    run_at(cpu, 0x0202, 0xA0, 0x08)
    assert cpu.y == 0x08


def test_sta_absolute_stores_accumulator(cpu):
    cpu.a = 0x9A
    run_at(cpu, 0x0200, 0x8D, 0x00, 0x03)
    assert cpu.bus.read8(0x0300) == 0x9A


def test_stx_and_sty_zero_page(cpu):
    cpu.x = 0x11
    cpu.y = 0x22
    run_at(cpu, 0x0200, 0x86, 0x50)
    run_at(cpu, 0x0202, 0x84, 0x51)
    assert cpu.bus.read8(0x0050) == 0x11
    assert cpu.bus.read8(0x0051) == 0x22
