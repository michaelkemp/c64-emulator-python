"""MOS 6526 CIA: ports, two timers, a TOD clock, a serial register, and
the interrupt control register shared by both C64 CIAs.

See docs/cia.md for the register map, the documented behavior this
implements (cited against the MOS 6526 preliminary datasheet), and the
known gaps (CNT pin, real serial bus timing). This module implements the
chip itself; `keyboard_matrix.py` and `joystick.py` implement the devices
CIA1's ports are wired to.
"""

from __future__ import annotations

from typing import Protocol

from c64.vic_ii import PAL_CLOCK_HZ

# Register offsets, mirrored every 16 bytes across each CIA's 256-byte
# window (see bus.py's CIA_WINDOW).
PRA, PRB, DDRA, DDRB = 0x0, 0x1, 0x2, 0x3
TALO, TAHI, TBLO, TBHI = 0x4, 0x5, 0x6, 0x7
TOD_10THS, TOD_SEC, TOD_MIN, TOD_HR = 0x8, 0x9, 0xA, 0xB
SDR, ICR, CRA, CRB = 0xC, 0xD, 0xE, 0xF

# On real hardware, TOD is driven by the AC mains frequency (50Hz PAL /
# 60Hz NTSC) fed into a divide-by-5 or divide-by-6 network to produce a
# 10Hz tick -- CRA bit 7 (TodClock.rate_50hz) just tells the chip which
# divisor to use for *that* external signal. This project has no such
# external TOD pin/mains input at all (nothing drives it), so -- same
# approach as VicII's raster timing and Sid's sample generation -- TOD is
# instead driven directly off real elapsed PHI2 cycles at the system
# clock rate, targeting exactly 10 ticks/real-second regardless of
# rate_50hz (which is still stored/read back correctly for software that
# checks it, it just doesn't change tick timing here). See docs/cia.md.
#
# PAL_CLOCK_HZ (985248) isn't evenly divisible by 10, so this is tracked
# in tenths-of-a-cycle (CIA6526._tod_tenth_cycle_accumulator) rather than
# as a fractional cycles-per-tenth float -- an all-integer accumulator,
# so accumulated float rounding can never make a long run of tick() calls
# drift from firing exactly 10 ticks per PAL_CLOCK_HZ cycles elapsed, no
# matter how the caller chunks those cycles across calls.
TOD_CYCLES_PER_TENTH = PAL_CLOCK_HZ / 10  # for callers estimating "about how many"

ICR_TIMER_A = 0x01
ICR_TIMER_B = 0x02
ICR_TOD_ALARM = 0x04
ICR_SDR = 0x08
ICR_FLAG = 0x10
ICR_IRQ = 0x80


class PortCoupler(Protocol):
    """What's physically wired across a CIA's two ports (CIA1 only, in
    practice: the keyboard matrix and joysticks -- see `Cia1Ports`)."""

    def sense_a(self, b_driven_low: int) -> int:
        """Bits externally pulled low on port A, given which port B bits
        are currently driven low."""
        ...

    def sense_b(self, a_driven_low: int) -> int:
        """Bits externally pulled low on port B, given which port A bits
        are currently driven low."""
        ...


class Timer:
    """A 6526 timer: 16-bit counter + latch, per docs/cia.md."""

    PHI2 = "phi2"
    CNT = "cnt"
    TIMER_A_UNDERFLOW = "timer_a_underflow"

    def __init__(self) -> None:
        self.latch = 0xFFFF
        self.value = 0xFFFF
        self.running = False
        self.one_shot = False
        self.count_source = self.PHI2
        self.pb_output_enabled = False
        self.pb_toggle_mode = False
        self.pb_state = False  # current level of the PBx output, if enabled

    def write_lo(self, value: int) -> None:
        self.latch = (self.latch & 0xFF00) | (value & 0xFF)

    def write_hi(self, value: int) -> None:
        self.latch = (self.latch & 0x00FF) | ((value & 0xFF) << 8)
        if not self.running:
            self.value = self.latch

    def read_lo(self) -> int:
        return self.value & 0xFF

    def read_hi(self) -> int:
        return (self.value >> 8) & 0xFF

    def force_load(self) -> None:
        self.value = self.latch

    def tick_phi2(self) -> bool:
        if not self.running or self.count_source != self.PHI2:
            return False
        return self._decrement()

    def tick_from_timer_a_underflow(self) -> bool:
        if not self.running or self.count_source != self.TIMER_A_UNDERFLOW:
            return False
        return self._decrement()

    def _decrement(self) -> bool:
        if self.value == 0:
            self.value = self.latch
            if self.one_shot:
                self.running = False
            self.pb_state = True if not self.pb_toggle_mode else not self.pb_state
            return True
        self.value -= 1
        self.pb_state = False
        return False


class TodClock:
    """BCD time-of-day clock with the latch-on-read/stop-on-write quirks
    documented in docs/cia.md."""

    def __init__(self) -> None:
        self.tenths, self.seconds, self.minutes, self.hours = 0, 0, 0, 0x01
        self.alarm = (0, 0, 0, 0x01)
        self._latched: tuple[int, int, int, int] | None = None
        self._running = True
        self.rate_50hz = False

    def _live(self) -> tuple[int, int, int, int]:
        return (self.tenths, self.seconds, self.minutes, self.hours)

    def read_tenths(self) -> int:
        self._latched = None  # reading tenths releases any hours-read latch
        return self._live()[0]

    def read_seconds(self) -> int:
        return (self._latched or self._live())[1]

    def read_minutes(self) -> int:
        return (self._latched or self._live())[2]

    def read_hours(self) -> int:
        self._latched = self._live()
        return self._latched[3]

    def write_tenths(self, value: int) -> None:
        self.tenths = value & 0x0F
        self._running = True

    def write_seconds(self, value: int) -> None:
        self.seconds = value & 0x7F

    def write_minutes(self, value: int) -> None:
        self.minutes = value & 0x7F

    def write_hours(self, value: int) -> None:
        self.hours = value & 0x9F
        self._running = False

    def tick_tenth(self) -> bool:
        """Advance the clock by 1/10s. Returns True if it now matches the
        alarm (an edge, i.e. fires once per match, not once per tick)."""
        if not self._running:
            return False
        matched_before = self._live() == self.alarm
        self.tenths = _bcd_increment(self.tenths, wrap_at=0x0A)
        if self.tenths == 0:
            self.seconds, carry = _bcd_increment_carry(self.seconds, wrap_at=0x60)
            if carry:
                self.minutes, carry = _bcd_increment_carry(self.minutes, wrap_at=0x60)
                if carry:
                    self.hours = _bcd_increment_hour(self.hours)
        matched_after = self._live() == self.alarm
        return matched_after and not matched_before


def _bcd_increment(value: int, wrap_at: int) -> int:
    value, _ = _bcd_increment_carry(value, wrap_at)
    return value


def _bcd_increment_carry(value: int, wrap_at: int) -> tuple[int, bool]:
    lo = value & 0x0F
    hi = value & 0xF0
    if lo == 9:
        lo = 0
        hi += 0x10
    else:
        lo += 1
    value = hi | lo
    if value >= wrap_at:
        return 0, True
    return value, False


def _bcd_increment_hour(hours: int) -> int:
    pm_bit = hours & 0x80
    hour = hours & 0x1F
    hour = _bcd_increment(hour, wrap_at=0x13)  # BCD 1-12, wraps after 12
    if hour == 0:
        hour = 0x01
        pm_bit ^= 0x80  # 12 -> 1 crosses the AM/PM boundary
    return pm_bit | hour


class CIA6526:
    """One MOS 6526 CIA. See docs/cia.md for the full behavior spec."""

    def __init__(self, *, port_coupler: PortCoupler | None = None) -> None:
        self.ddra = 0x00
        self.ddrb = 0x00
        self._latch_a = 0x00
        self._latch_b = 0x00
        self.port_coupler = port_coupler

        self.timer_a = Timer()
        self.timer_b = Timer()
        self.tod = TodClock()

        self._sdr = 0x00
        self._sp_output_mode = False
        self._icr_mask = 0x00
        self._icr_flags = 0x00
        self._crb_alarm = False
        self._tod_tenth_cycle_accumulator = 0  # units of 1/10 PHI2 cycle -- see TOD_CYCLES_PER_TENTH

    # -- ports --------------------------------------------------------

    @staticmethod
    def _driven_low(ddr: int, latch: int) -> int:
        return ddr & ~latch & 0xFF

    def read_port_a(self) -> int:
        external = 0
        if self.port_coupler is not None:
            external = self.port_coupler.sense_a(self._driven_low(self.ddrb, self._latch_b))
        value = (self.ddra & self._latch_a) | (~self.ddra & ~external & 0xFF)
        return value & 0xFF

    def read_port_b(self) -> int:
        external = 0
        if self.port_coupler is not None:
            external = self.port_coupler.sense_b(self._driven_low(self.ddra, self._latch_a))
        value = (self.ddrb & self._latch_b) | (~self.ddrb & ~external & 0xFF)
        if self.timer_a.pb_output_enabled:
            value = _set_bit(value, 6, self.timer_a.pb_state)
        if self.timer_b.pb_output_enabled:
            value = _set_bit(value, 7, self.timer_b.pb_state)
        return value & 0xFF

    # -- register file --------------------------------------------------

    def read_register(self, offset: int) -> int:
        if offset == PRA:
            return self.read_port_a()
        if offset == PRB:
            return self.read_port_b()
        if offset == DDRA:
            return self.ddra
        if offset == DDRB:
            return self.ddrb
        if offset == TALO:
            return self.timer_a.read_lo()
        if offset == TAHI:
            return self.timer_a.read_hi()
        if offset == TBLO:
            return self.timer_b.read_lo()
        if offset == TBHI:
            return self.timer_b.read_hi()
        if offset == TOD_10THS:
            return self.tod.read_tenths()
        if offset == TOD_SEC:
            return self.tod.read_seconds()
        if offset == TOD_MIN:
            return self.tod.read_minutes()
        if offset == TOD_HR:
            return self.tod.read_hours()
        if offset == SDR:
            return self._sdr
        if offset == ICR:
            return self._read_icr()
        if offset == CRA:
            return self._read_cra()
        if offset == CRB:
            return self._read_crb()
        raise ValueError(f"invalid CIA register offset: {offset}")

    def write_register(self, offset: int, value: int) -> None:
        value &= 0xFF
        if offset == PRA:
            self._latch_a = value
        elif offset == PRB:
            self._latch_b = value
        elif offset == DDRA:
            self.ddra = value
        elif offset == DDRB:
            self.ddrb = value
        elif offset == TALO:
            self.timer_a.write_lo(value)
        elif offset == TAHI:
            self.timer_a.write_hi(value)
        elif offset == TBLO:
            self.timer_b.write_lo(value)
        elif offset == TBHI:
            self.timer_b.write_hi(value)
        elif offset == TOD_10THS:
            self._write_tod_or_alarm(0, value)
        elif offset == TOD_SEC:
            self._write_tod_or_alarm(1, value)
        elif offset == TOD_MIN:
            self._write_tod_or_alarm(2, value)
        elif offset == TOD_HR:
            self._write_tod_or_alarm(3, value)
        elif offset == SDR:
            self._write_sdr(value)
        elif offset == ICR:
            self._write_icr(value)
        elif offset == CRA:
            self._write_cra(value)
        elif offset == CRB:
            self._write_crb(value)
        else:
            raise ValueError(f"invalid CIA register offset: {offset}")

    # -- TOD / alarm register routing ------------------------------------

    def _write_tod_or_alarm(self, field: int, value: int) -> None:
        if self._crb_alarm:
            tenths, seconds, minutes, hours = self.tod.alarm
            fields = [tenths, seconds, minutes, hours]
            fields[field] = value & (0x0F if field == 0 else (0x9F if field == 3 else 0x7F))
            self.tod.alarm = tuple(fields)
            return
        (
            self.tod.write_tenths,
            self.tod.write_seconds,
            self.tod.write_minutes,
            self.tod.write_hours,
        )[field](value)

    # -- serial data register --------------------------------------------

    def _write_sdr(self, value: int) -> None:
        self._sdr = value
        if self._sp_output_mode:
            # No real serial device/CNT source (see docs/cia.md): the
            # shift "completes" immediately instead of over 8 CNT pulses.
            self._icr_flags |= ICR_SDR

    # -- interrupt control register ---------------------------------------

    def _read_icr(self) -> int:
        pending = self._icr_flags
        asserted = bool(pending & self._icr_mask)
        result = pending | (ICR_IRQ if asserted else 0)
        self._icr_flags = 0
        return result

    def _write_icr(self, value: int) -> None:
        bits = value & 0x1F
        if value & ICR_IRQ:
            self._icr_mask |= bits
        else:
            self._icr_mask &= ~bits & 0xFF

    @property
    def irq_line(self) -> bool:
        return bool(self._icr_flags & self._icr_mask)

    # -- control registers --------------------------------------------------

    def _read_cra(self) -> int:
        t = self.timer_a
        return (
            int(t.running)
            | (int(t.pb_output_enabled) << 1)
            | (int(t.pb_toggle_mode) << 2)
            | (int(t.one_shot) << 3)
            | (int(t.count_source == Timer.CNT) << 5)
            | (int(self._sp_output_mode) << 6)
            | (int(self.tod.rate_50hz) << 7)
        )

    def _write_cra(self, value: int) -> None:
        t = self.timer_a
        t.running = bool(value & 0x01)
        t.pb_output_enabled = bool(value & 0x02)
        t.pb_toggle_mode = bool(value & 0x04)
        t.one_shot = bool(value & 0x08)
        if value & 0x10:
            t.force_load()
        t.count_source = Timer.CNT if value & 0x20 else Timer.PHI2
        self._sp_output_mode = bool(value & 0x40)
        self.tod.rate_50hz = bool(value & 0x80)

    def _read_crb(self) -> int:
        t = self.timer_b
        inmode = {Timer.PHI2: 0, Timer.CNT: 1, Timer.TIMER_A_UNDERFLOW: 2}[t.count_source]
        return (
            int(t.running)
            | (int(t.pb_output_enabled) << 1)
            | (int(t.pb_toggle_mode) << 2)
            | (int(t.one_shot) << 3)
            | (inmode << 5)
            | (int(self._crb_alarm) << 7)
        )

    def _write_crb(self, value: int) -> None:
        t = self.timer_b
        t.running = bool(value & 0x01)
        t.pb_output_enabled = bool(value & 0x02)
        t.pb_toggle_mode = bool(value & 0x04)
        t.one_shot = bool(value & 0x08)
        if value & 0x10:
            t.force_load()
        inmode = (value >> 5) & 0x03
        t.count_source = (Timer.PHI2, Timer.CNT, Timer.TIMER_A_UNDERFLOW, Timer.TIMER_A_UNDERFLOW)[inmode]
        self._crb_alarm = bool(value & 0x80)

    # -- driving the chip forward in time -----------------------------------

    def tick(self, cycles: int = 1) -> None:
        for _ in range(cycles):
            underflow_a = self.timer_a.tick_phi2()
            underflow_b_phi2 = self.timer_b.tick_phi2()
            underflow_b_a = self.timer_b.tick_from_timer_a_underflow() if underflow_a else False
            if underflow_a:
                self._icr_flags |= ICR_TIMER_A
            if underflow_b_phi2 or underflow_b_a:
                self._icr_flags |= ICR_TIMER_B

        self._tod_tenth_cycle_accumulator += cycles * 10
        while self._tod_tenth_cycle_accumulator >= PAL_CLOCK_HZ:
            self._tod_tenth_cycle_accumulator -= PAL_CLOCK_HZ
            self.tick_tenth_second()

    def tick_tenth_second(self) -> None:
        if self.tod.tick_tenth():
            self._icr_flags |= ICR_TOD_ALARM


def _set_bit(value: int, bit: int, on: bool) -> int:
    mask = 1 << bit
    return (value | mask) if on else (value & ~mask)
