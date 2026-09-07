from .helpers import run_at


def test_adc_binary_basic(cpu):
    cpu.a = 0x01
    cpu.flags.c = False
    run_at(cpu, 0x0200, 0x69, 0x01)
    assert cpu.a == 0x02
    assert cpu.flags.c is False


def test_adc_binary_carry_out(cpu):
    cpu.a = 0xFF
    cpu.flags.c = False
    run_at(cpu, 0x0200, 0x69, 0x01)
    assert cpu.a == 0x00
    assert cpu.flags.c is True
    assert cpu.flags.z is True


def test_adc_binary_signed_overflow(cpu):
    # 0x50 + 0x50 = 0xA0: two positives producing a negative result -> V set
    cpu.a = 0x50
    cpu.flags.c = False
    run_at(cpu, 0x0200, 0x69, 0x50)
    assert cpu.a == 0xA0
    assert cpu.flags.v is True
    assert cpu.flags.n is True


def test_adc_honors_incoming_carry(cpu):
    cpu.a = 0x01
    cpu.flags.c = True
    run_at(cpu, 0x0200, 0x69, 0x01)
    assert cpu.a == 0x03


def test_sbc_binary_basic_no_borrow(cpu):
    cpu.a = 0x05
    cpu.flags.c = True  # carry set means "no borrow" going in
    run_at(cpu, 0x0200, 0xE9, 0x03)
    assert cpu.a == 0x02
    assert cpu.flags.c is True  # no borrow occurred


def test_sbc_binary_with_borrow(cpu):
    cpu.a = 0x03
    cpu.flags.c = True
    run_at(cpu, 0x0200, 0xE9, 0x05)
    assert cpu.a == 0xFE  # 3 - 5 wraps
    assert cpu.flags.c is False  # borrow occurred


def test_adc_decimal_mode_basic(cpu):
    cpu.flags.d = True
    cpu.flags.c = False
    cpu.a = 0x09
    run_at(cpu, 0x0200, 0x69, 0x01)  # 09 + 01 in BCD == 10
    assert cpu.a == 0x10
    assert cpu.flags.c is False


def test_adc_decimal_mode_carries_out(cpu):
    cpu.flags.d = True
    cpu.flags.c = False
    cpu.a = 0x99
    run_at(cpu, 0x0200, 0x69, 0x01)  # 99 + 01 in BCD == 100 -> 00 with carry
    assert cpu.a == 0x00
    assert cpu.flags.c is True
