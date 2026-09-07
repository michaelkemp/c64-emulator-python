"""MOS 6581/8580 SID: three voices (oscillator + ADSR envelope), a simple
digital filter, and a master volume stage.

See docs/sid.md for the register map, the oscillator/envelope/filter
algorithms (and exactly which parts are approximations, not bit-exact --
this is explicitly the chip docs/roadmap.md calls "the most forgiving to
get close enough early"), and known gaps.
"""

from __future__ import annotations

import math

from c64.vic_ii import PAL_CLOCK_HZ

FREQLO, FREQHI = 0x00, 0x01
PWLO, PWHI = 0x02, 0x03
CR = 0x04
AD, SR = 0x05, 0x06
VOICE_STRIDE = 7
NUM_VOICES = 3

FILTER_CUTOFF_LO, FILTER_CUTOFF_HI = 0x15, 0x16
FILTER_RES_ROUTE = 0x17
MODE_VOLUME = 0x18
POTX, POTY = 0x19, 0x1A
OSC3, ENV3 = 0x1B, 0x1C

NUM_REGISTERS = 0x1D  # $1D-$1F are unconnected

GATE = 0x01
SYNC = 0x02
RING_MOD = 0x04
TEST = 0x08
WAVEFORM_TRIANGLE = 0x10
WAVEFORM_SAWTOOTH = 0x20
WAVEFORM_PULSE = 0x40
WAVEFORM_NOISE = 0x80

ACCUMULATOR_MASK = (1 << 24) - 1

# From the real MOS 6581 datasheet (verified against a transcription of
# it, not recalled unchecked) -- see docs/sid.md.
ATTACK_MS = [2, 8, 16, 24, 38, 56, 68, 80, 100, 250, 500, 800, 1000, 3000, 5000, 8000]
DECAY_RELEASE_MS = [6, 24, 48, 72, 114, 168, 204, 240, 300, 750, 1500, 2400, 3000, 9000, 15000, 24000]

# Sync/ring-mod source: voice n's source is the *previous* voice in this
# circular order (1<-3, 2<-1, 3<-2 in 1-based datasheet numbering).
SOURCE_VOICE = {0: 2, 1: 0, 2: 1}


def _cycles_for_rate(ms: float, steps: int = 255) -> int:
    return max(1, round(ms / 1000 * PAL_CLOCK_HZ / steps))


ATTACK_PERIODS = [_cycles_for_rate(ms) for ms in ATTACK_MS]
DECAY_RELEASE_PERIODS = [_cycles_for_rate(ms) for ms in DECAY_RELEASE_MS]


def _exponential_zone_divisor(level: int) -> int:
    """The commonly-published decay/release zone approximation -- see
    docs/sid.md's ADSR section."""
    if level > 92:
        return 1
    if level > 53:
        return 2
    if level > 25:
        return 4
    if level > 13:
        return 8
    if level > 5:
        return 16
    return 30


class Voice:
    def __init__(self) -> None:
        self.freq = 0
        self.pulse_width = 0
        self.control = 0
        self.attack = 0
        self.decay = 0
        self.sustain = 0
        self.release = 0

        self.accumulator = 0
        self.envelope = 0
        self._noise_lfsr = 0x7FFFFF
        self._phase = "release"
        self._rate_counter = 0

    @property
    def gate(self) -> bool:
        return bool(self.control & GATE)

    @property
    def sync_enabled(self) -> bool:
        return bool(self.control & SYNC)

    @property
    def ring_mod_enabled(self) -> bool:
        return bool(self.control & RING_MOD)

    @property
    def test(self) -> bool:
        return bool(self.control & TEST)

    @property
    def waveform_bits(self) -> int:
        return self.control & 0xF0

    @property
    def sustain_level(self) -> int:
        return self.sustain | (self.sustain << 4)

    def write_control(self, value: int) -> None:
        was_gated = self.gate
        self.control = value
        if self.gate and not was_gated:
            self._phase = "attack"
        elif not self.gate and was_gated:
            self._phase = "release"

    # -- per-cycle advancement --------------------------------------------

    def advance_accumulator(self) -> None:
        if self.test:
            self.accumulator = 0
            return
        old_bit19 = (self.accumulator >> 19) & 1
        self.accumulator = (self.accumulator + self.freq) & ACCUMULATOR_MASK
        if (self.accumulator >> 19) & 1 and not old_bit19:
            self._clock_noise()

    def _clock_noise(self) -> None:
        feedback = ((self._noise_lfsr >> 22) ^ (self._noise_lfsr >> 17)) & 1
        self._noise_lfsr = ((self._noise_lfsr << 1) | feedback) & 0x7FFFFF

    def tick_envelope(self) -> None:
        if self._phase == "attack":
            period = ATTACK_PERIODS[self.attack]
        elif self._phase in ("decay", "sustain"):
            period = DECAY_RELEASE_PERIODS[self.decay] * _exponential_zone_divisor(self.envelope)
        elif self._phase == "release":
            period = DECAY_RELEASE_PERIODS[self.release] * _exponential_zone_divisor(self.envelope)
        else:
            return

        self._rate_counter += 1
        if self._rate_counter < period:
            return
        self._rate_counter = 0

        if self._phase == "attack":
            self.envelope = min(255, self.envelope + 1)
            if self.envelope == 255:
                self._phase = "decay"
        elif self._phase in ("decay", "sustain"):
            target = self.sustain_level
            if self.envelope > target:
                self.envelope -= 1
                self._phase = "decay"
            else:
                self._phase = "sustain"
        elif self._phase == "release":
            self.envelope = max(0, self.envelope - 1)

    # -- waveform output (12-bit unsigned) ---------------------------------

    def _sawtooth(self) -> int:
        return (self.accumulator >> 12) & 0xFFF

    def _triangle(self, ring_source_msb: int) -> int:
        msb = (self.accumulator >> 23) & 1
        if self.ring_mod_enabled:
            msb ^= ring_source_msb
        shifted = (self.accumulator << 1) & 0x1FFFFFF
        if msb:
            shifted ^= 0x1FFFFFF
        return (shifted >> 12) & 0xFFF

    def _pulse(self) -> int:
        return 0xFFF if ((self.accumulator >> 12) & 0xFFF) >= self.pulse_width else 0x000

    def _noise(self) -> int:
        lfsr = self._noise_lfsr
        taps = (20, 18, 14, 11, 9, 5, 2, 0)
        value = 0
        for i, bit in enumerate(taps):
            value |= ((lfsr >> bit) & 1) << (7 - i)
        return value << 4

    def waveform_output(self, ring_source_msb: int) -> int:
        bits = self.waveform_bits
        if bits == 0:
            return 0
        value = 0xFFF
        if bits & WAVEFORM_TRIANGLE:
            value &= self._triangle(ring_source_msb)
        if bits & WAVEFORM_SAWTOOTH:
            value &= self._sawtooth()
        if bits & WAVEFORM_PULSE:
            value &= self._pulse()
        if bits & WAVEFORM_NOISE:
            value &= self._noise()
        return value


class StateVariableFilter:
    """Generic digital state-variable (Chamberlin) filter -- not derived
    from reSID, see docs/sid.md."""

    def __init__(self) -> None:
        self.low = 0.0
        self.band = 0.0

    def process(self, input_signal: float, cutoff_hz: float, resonance_q: float, sample_rate: int):
        cutoff_hz = min(cutoff_hz, sample_rate / 4.0)
        f = 2.0 * math.sin(math.pi * cutoff_hz / sample_rate)
        q = 1.0 / max(resonance_q, 0.5)
        high = input_signal - self.low - q * self.band
        self.band += f * high
        self.low += f * self.band
        return self.low, self.band, high


class Sid:
    def __init__(self, sample_rate: int = 44100) -> None:
        self.voices = [Voice(), Voice(), Voice()]
        self._registers = bytearray(NUM_REGISTERS)
        self.sample_rate = sample_rate
        self._filter = StateVariableFilter()

    # -- register file --------------------------------------------------

    def read_register(self, offset: int) -> int:
        if offset >= NUM_REGISTERS:
            return 0xFF
        if offset < NUM_VOICES * VOICE_STRIDE or offset in (
            FILTER_CUTOFF_LO,
            FILTER_CUTOFF_HI,
            FILTER_RES_ROUTE,
            MODE_VOLUME,
            POTX,
            POTY,
        ):
            return 0xFF  # write-only on real hardware -- see docs/sid.md
        if offset == OSC3:
            source = (self.voices[SOURCE_VOICE[2]].accumulator >> 23) & 1
            return (self.voices[2].waveform_output(source) >> 4) & 0xFF
        if offset == ENV3:
            return self.voices[2].envelope
        return 0xFF

    def write_register(self, offset: int, value: int) -> None:
        value &= 0xFF
        if offset >= NUM_REGISTERS:
            return
        if offset < NUM_VOICES * VOICE_STRIDE:
            voice = self.voices[offset // VOICE_STRIDE]
            reg = offset % VOICE_STRIDE
            if reg == FREQLO:
                voice.freq = (voice.freq & 0xFF00) | value
            elif reg == FREQHI:
                voice.freq = (voice.freq & 0x00FF) | (value << 8)
            elif reg == PWLO:
                voice.pulse_width = (voice.pulse_width & 0xF00) | value
            elif reg == PWHI:
                voice.pulse_width = (voice.pulse_width & 0x0FF) | ((value & 0x0F) << 8)
            elif reg == CR:
                voice.write_control(value)
            elif reg == AD:
                voice.attack = (value >> 4) & 0x0F
                voice.decay = value & 0x0F
            elif reg == SR:
                voice.sustain = (value >> 4) & 0x0F
                voice.release = value & 0x0F
            return
        if offset in (POTX, POTY, OSC3, ENV3):
            return  # read-only
        self._registers[offset] = value

    # -- filter parameters --------------------------------------------------

    @property
    def cutoff_hz(self) -> float:
        raw = (self._registers[FILTER_CUTOFF_HI] << 3) | (self._registers[FILTER_CUTOFF_LO] & 0x07)
        return 30.0 + (raw / 2047.0) * (12_000.0 - 30.0)

    @property
    def resonance_q(self) -> float:
        raw = (self._registers[FILTER_RES_ROUTE] >> 4) & 0x0F
        return 1.0 + raw * 0.5

    # -- driving the chip forward in time -----------------------------------

    def tick(self, cycles: int) -> None:
        for _ in range(cycles):
            self._tick_one_cycle()

    def _tick_one_cycle(self) -> None:
        prev_msbs = [(v.accumulator >> 23) & 1 for v in self.voices]
        for v in self.voices:
            v.advance_accumulator()
        new_msbs = [(v.accumulator >> 23) & 1 for v in self.voices]
        for i, v in enumerate(self.voices):
            source = SOURCE_VOICE[i]
            if v.sync_enabled and prev_msbs[source] == 1 and new_msbs[source] == 0:
                v.accumulator = 0
        for v in self.voices:
            v.tick_envelope()

    # -- audio output ------------------------------------------------------

    def output_sample(self) -> float:
        msbs = [(v.accumulator >> 23) & 1 for v in self.voices]
        voice3_disconnected = bool(self._registers[MODE_VOLUME] & 0x80)
        filter_select = self._registers[FILTER_RES_ROUTE] & 0x07

        filtered_input = 0.0
        unfiltered = 0.0
        for i, v in enumerate(self.voices):
            if i == 2 and voice3_disconnected:
                continue
            waveform = v.waveform_output(msbs[SOURCE_VOICE[i]])
            centered = (waveform - 2048.0) / 2048.0  # bipolar -1..1, DC-removed
            signed = centered * (v.envelope / 255.0)  # then scale amplitude by envelope
            if filter_select & (1 << i):
                filtered_input += signed
            else:
                unfiltered += signed

        low, band, high = self._filter.process(
            filtered_input, self.cutoff_hz, self.resonance_q, self.sample_rate
        )
        mode = self._registers[MODE_VOLUME]
        mixed_filtered = 0.0
        if mode & 0x10:
            mixed_filtered += low
        if mode & 0x20:
            mixed_filtered += band
        if mode & 0x40:
            mixed_filtered += high

        volume = (mode & 0x0F) / 15.0
        total = (unfiltered + mixed_filtered) * volume
        return max(-1.0, min(1.0, total))
