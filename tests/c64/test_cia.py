import pytest

from c64.cia import CIA6526, ICR, CRA, CRB, PRA, PRB, DDRA, DDRB, TALO, TAHI, TBLO, TBHI, SDR


@pytest.fixture
def cia():
    return CIA6526()


def test_port_output_reads_back_the_latch(cia):
    cia.write_register(DDRA, 0xFF)
    cia.write_register(PRA, 0x42)
    assert cia.read_register(PRA) == 0x42


def test_port_input_bits_float_high_without_a_coupler(cia):
    cia.write_register(DDRA, 0x00)
    cia.write_register(PRA, 0x00)  # irrelevant for input-configured bits
    assert cia.read_register(PRA) == 0xFF


class FakeCoupler:
    def __init__(self, a_pulldown=0, b_pulldown=0):
        self.a_pulldown = a_pulldown
        self.b_pulldown = b_pulldown
        self.seen_b_driven_low = None
        self.seen_a_driven_low = None

    def sense_a(self, b_driven_low):
        self.seen_b_driven_low = b_driven_low
        return self.a_pulldown

    def sense_b(self, a_driven_low):
        self.seen_a_driven_low = a_driven_low
        return self.b_pulldown


def test_port_coupler_pulls_input_bits_low():
    coupler = FakeCoupler(b_pulldown=0b0000_0101)
    cia = CIA6526(port_coupler=coupler)
    cia.write_register(DDRA, 0xFF)
    cia.write_register(PRA, 0b1111_1110)  # drive bit 0 low, rest high
    cia.write_register(DDRB, 0x00)  # port B all inputs

    assert cia.read_register(PRB) == 0xFF & ~0b0000_0101 & 0xFF
    assert coupler.seen_a_driven_low == 0b0000_0001


def test_timer_a_loads_immediately_when_stopped(cia):
    cia.write_register(TALO, 0x34)
    cia.write_register(TAHI, 0x12)
    assert cia.timer_a.value == 0x1234


def test_timer_a_high_byte_write_only_updates_latch_while_running(cia):
    cia.write_register(TALO, 0x00)
    cia.write_register(TAHI, 0x10)  # latch=0x1000, counter loaded (stopped)
    cia.write_register(CRA, 0x01)  # start
    cia.write_register(TAHI, 0x20)  # latch=0x2000, counter NOT reloaded now
    assert cia.timer_a.latch == 0x2000
    assert cia.timer_a.value == 0x1000


def test_timer_a_counts_down_and_underflows(cia):
    cia.write_register(TALO, 0x02)
    cia.write_register(TAHI, 0x00)
    cia.write_register(CRA, 0x01)  # start, continuous
    cia.tick(2)
    assert cia.timer_a.value == 0x0000
    cia.tick(1)  # underflow: reloads from latch, sets ICR flag
    assert cia.timer_a.value == 0x0002
    assert cia.read_register(ICR) & 0x01


def test_timer_a_one_shot_stops_itself_on_underflow(cia):
    cia.write_register(TALO, 0x00)
    cia.write_register(TAHI, 0x00)
    cia.write_register(CRA, 0x01 | 0x08)  # start, one-shot
    cia.tick(1)
    assert cia.timer_a.running is False


def test_force_load_strobe_reloads_counter_without_starting(cia):
    cia.write_register(TALO, 0x99)
    cia.write_register(TAHI, 0x00)
    cia.write_register(CRA, 0x01)  # start
    cia.tick(0x50)
    cia.write_register(TALO, 0x11)
    cia.write_register(TAHI, 0x22)  # only updates latch, timer is running
    cia.write_register(CRA, 0x01 | 0x10)  # force load strobe while still running
    assert cia.timer_a.value == 0x2211
    assert cia.timer_a.running is True


def test_timer_b_can_count_timer_a_underflows(cia):
    cia.write_register(TALO, 0x01)
    cia.write_register(TAHI, 0x00)
    cia.write_register(CRA, 0x01)  # timer A: start, continuous, counts phi2

    cia.write_register(TBLO, 0x03)
    cia.write_register(TBHI, 0x00)
    cia.write_register(CRB, 0x01 | (0b10 << 5))  # timer B: start, count timer A underflow

    cia.tick(2)  # timer A underflows once (after 2 ticks: 1->0->underflow)
    assert cia.timer_b.value == 0x0002
    assert cia.read_register(ICR) & 0x02 == 0  # not yet -- timer B hasn't underflowed

    for _ in range(2):
        cia.tick(2)  # two more timer A underflow cycles
    assert cia.timer_b.value == 0x0000


def test_icr_read_clears_pending_flags(cia):
    cia.write_register(TALO, 0x00)
    cia.write_register(TAHI, 0x00)
    cia.write_register(CRA, 0x01)
    cia.tick(1)
    assert cia.read_register(ICR) & 0x01
    assert cia.read_register(ICR) == 0  # cleared by the read above


def test_icr_write_sets_and_clears_mask_bits(cia):
    cia.write_register(ICR, 0x81)  # set bit 0 in the mask
    assert cia._icr_mask == 0x01
    cia.write_register(ICR, 0x03)  # clear bits 0-1 (bit 7 clear = "clear" op)
    assert cia._icr_mask == 0x00


def test_irq_line_true_once_mask_enables_a_pending_flag(cia):
    cia.write_register(TALO, 0x00)
    cia.write_register(TAHI, 0x00)
    cia.write_register(CRA, 0x01)
    cia.tick(1)  # sets pending flag, mask is empty -> not asserted
    assert cia.irq_line is False
    cia.write_register(ICR, 0x81)  # enable timer A -- flag is still pending
    assert cia.irq_line is True


def test_sdr_output_mode_completes_immediately(cia):
    cia.write_register(CRA, 0x40)  # SPMODE=1 (output), timer stopped
    cia.write_register(SDR, 0xAB)
    assert cia.read_register(ICR) & 0x08
    assert cia.read_register(SDR) == 0xAB


def test_tod_write_hours_stops_clock_write_tenths_restarts_it(cia):
    cia.tick_tenth_second()  # runs by default
    assert cia.tod.tenths == 1

    cia.write_register(0xB, 0x01)  # TOD_HR -- stops the clock
    cia.tick_tenth_second()
    assert cia.tod.tenths == 1  # unchanged, clock stopped

    cia.write_register(0x8, 0x00)  # TOD_10THS -- restarts it
    cia.tick_tenth_second()
    assert cia.tod.tenths == 1


def test_tod_reading_hours_latches_until_tenths_is_read(cia):
    for _ in range(9):
        cia.tick_tenth_second()
    assert cia.tod.read_hours() == 0x01
    cia.tick_tenth_second()  # seconds rolls to 01 internally
    assert cia.tod.read_seconds() == 0x00  # still latched
    cia.tod.read_tenths()  # releases the latch
    assert cia.tod.read_seconds() == 0x01


def test_tod_alarm_fires_icr_flag_once_on_match(cia):
    cia.tod.alarm = (0x02, 0, 0, 0x01)
    cia.write_register(CRB, 0x00)  # ALARM bit clear -- $8-$B write the clock
    cia.tick_tenth_second()
    assert cia.read_register(ICR) == 0
    cia.tick_tenth_second()  # tenths now 0x02, matches alarm
    assert cia.read_register(ICR) & 0x04
    cia.tick_tenth_second()
    assert cia.read_register(ICR) & 0x04 == 0  # only fires on the matching edge
