import pytest

from c64.sid import (
    AD,
    ATTACK_PERIODS,
    CR,
    DECAY_RELEASE_PERIODS,
    ENV3,
    FILTER_CUTOFF_HI,
    FILTER_CUTOFF_LO,
    FILTER_RES_ROUTE,
    FREQHI,
    FREQLO,
    GATE,
    MODE_VOLUME,
    OSC3,
    PWHI,
    PWLO,
    RING_MOD,
    SR,
    SYNC,
    TEST,
    VOICE_STRIDE,
    WAVEFORM_NOISE,
    WAVEFORM_PULSE,
    WAVEFORM_SAWTOOTH,
    WAVEFORM_TRIANGLE,
    Sid,
    _exponential_zone_divisor,
)


@pytest.fixture
def sid():
    return Sid()


def voice_offset(n, reg):
    return n * VOICE_STRIDE + reg


def test_frequency_register_combines_lo_and_hi(sid):
    sid.write_register(voice_offset(0, FREQLO), 0x34)
    sid.write_register(voice_offset(0, FREQHI), 0x12)
    assert sid.voices[0].freq == 0x1234


def test_pulse_width_register_combines_lo_and_high_nibble(sid):
    sid.write_register(voice_offset(0, PWLO), 0xFF)
    sid.write_register(voice_offset(0, PWHI), 0xFA)  # only low nibble used
    assert sid.voices[0].pulse_width == 0xAFF


def test_ad_sr_registers_decode_all_four_nibbles(sid):
    sid.write_register(voice_offset(0, AD), 0x5A)
    sid.write_register(voice_offset(0, SR), 0x3C)
    v = sid.voices[0]
    assert (v.attack, v.decay, v.sustain, v.release) == (0x5, 0xA, 0x3, 0xC)


def test_voice_and_filter_registers_are_write_only(sid):
    sid.write_register(voice_offset(0, FREQLO), 0x42)
    assert sid.read_register(voice_offset(0, FREQLO)) == 0xFF
    sid.write_register(MODE_VOLUME, 0x0F)
    assert sid.read_register(MODE_VOLUME) == 0xFF


def test_unconnected_registers_are_open_bus(sid):
    sid.write_register(0x1D, 0x55)
    assert sid.read_register(0x1D) == 0xFF
    assert sid.read_register(0x1F) == 0xFF


def test_osc3_reflects_voice_three_waveform_output(sid):
    sid.write_register(voice_offset(2, FREQLO), 0xFF)
    sid.write_register(voice_offset(2, FREQHI), 0x0F)
    sid.write_register(voice_offset(2, CR), WAVEFORM_SAWTOOTH)
    sid.tick(1000)
    expected = (sid.voices[2].waveform_output(0) >> 4) & 0xFF
    assert sid.read_register(OSC3) == expected


def test_env3_reflects_voice_three_envelope(sid):
    sid.write_register(voice_offset(2, AD), 0x00)  # fastest attack
    sid.write_register(voice_offset(2, CR), GATE)
    sid.tick(ATTACK_PERIODS[0] * 300)
    assert sid.read_register(ENV3) == sid.voices[2].envelope
    assert sid.voices[2].envelope > 0


def test_sawtooth_ramps_linearly_with_frequency():
    sid = Sid()
    sid.write_register(voice_offset(0, FREQLO), 0x00)
    sid.write_register(voice_offset(0, FREQHI), 0x10)  # freq = 0x1000
    sid.write_register(voice_offset(0, CR), WAVEFORM_SAWTOOTH)
    outputs = []
    for _ in range(5):
        outputs.append(sid.voices[0].waveform_output(0))
        sid.tick(1)
    assert outputs == sorted(outputs)  # monotonically non-decreasing
    assert len(set(outputs)) > 1  # actually changing


def test_zero_frequency_holds_sawtooth_output_constant():
    sid = Sid()
    sid.write_register(voice_offset(0, CR), WAVEFORM_SAWTOOTH)
    before = sid.voices[0].waveform_output(0)
    sid.tick(10_000)
    assert sid.voices[0].waveform_output(0) == before == 0


def test_pulse_waveform_switches_at_the_pulse_width_threshold():
    sid = Sid()
    v = sid.voices[0]
    v.pulse_width = 0x800
    v.control = WAVEFORM_PULSE
    v.accumulator = 0x7FF << 12
    assert v.waveform_output(0) == 0x000
    v.accumulator = 0x800 << 12
    assert v.waveform_output(0) == 0xFFF


def test_test_bit_holds_accumulator_at_zero():
    sid = Sid()
    sid.write_register(voice_offset(0, FREQHI), 0xFF)
    sid.write_register(voice_offset(0, CR), TEST)
    sid.tick(1000)
    assert sid.voices[0].accumulator == 0


def test_combined_waveforms_and_the_outputs_together():
    sid = Sid()
    v = sid.voices[0]
    v.control = WAVEFORM_SAWTOOTH | WAVEFORM_PULSE
    v.pulse_width = 0x000  # pulse always high (0xFFF) at any accumulator position
    v.accumulator = 0x123 << 12
    sawtooth_alone = 0x123
    assert v.waveform_output(0) == sawtooth_alone & 0xFFF  # ANDed with all-1s pulse -> unchanged


def test_hard_sync_resets_the_synced_voice_when_source_wraps():
    sid = Sid()
    source, synced = sid.voices[2], sid.voices[0]  # voice 0's source is voice 2
    source.freq = 0xFFFF
    source.control = WAVEFORM_SAWTOOTH
    source.accumulator = (1 << 24) - 1  # about to overflow
    synced.freq = 0x1000
    synced.control = WAVEFORM_SAWTOOTH | SYNC
    synced.accumulator = 0x800000  # nonzero, would NOT naturally be near 0 next tick

    sid.tick(1)
    assert synced.accumulator < 0x1000  # reset to (near) zero by the sync


def test_ring_modulation_only_affects_triangle_and_needs_a_source_wraparound():
    sid = Sid()
    v = sid.voices[1]  # voice 1's source is voice 0
    v.control = WAVEFORM_TRIANGLE | RING_MOD
    v.accumulator = 0x400000  # top bit clear
    without_ring = v.waveform_output(ring_source_msb=0)
    with_ring = v.waveform_output(ring_source_msb=1)
    assert without_ring != with_ring


def test_noise_lfsr_changes_over_time_and_is_deterministic():
    sid_a = Sid()
    sid_b = Sid()
    for sid in (sid_a, sid_b):
        sid.write_register(voice_offset(0, FREQHI), 0xFF)
        sid.write_register(voice_offset(0, CR), WAVEFORM_NOISE)

    first = sid_a.voices[0].waveform_output(0)
    sid_a.tick(200)
    sid_b.tick(200)
    later_a = sid_a.voices[0].waveform_output(0)
    later_b = sid_b.voices[0].waveform_output(0)

    assert later_a != first  # it actually changes
    assert later_a == later_b  # deterministic given identical inputs


def test_exponential_zone_divisor_boundaries():
    assert _exponential_zone_divisor(255) == 1
    assert _exponential_zone_divisor(93) == 1
    assert _exponential_zone_divisor(92) == 2
    assert _exponential_zone_divisor(54) == 2
    assert _exponential_zone_divisor(53) == 4
    assert _exponential_zone_divisor(6) == 16
    assert _exponential_zone_divisor(5) == 30
    assert _exponential_zone_divisor(0) == 30


def test_envelope_attacks_to_255_then_decays_to_sustain_then_releases():
    sid = Sid()
    v = sid.voices[0]
    sid.write_register(voice_offset(0, AD), 0x00)  # fastest attack AND fastest decay
    sid.write_register(voice_offset(0, SR), 0x80)  # sustain level 8 -> target 0x88

    sid.write_register(voice_offset(0, CR), GATE)
    # Tick exactly the cycles needed for the 255 attack steps -- not a
    # moment more: overshooting bleeds into decay, which (unlike sustain
    # or release-at-zero) keeps actively changing the envelope, making an
    # approximate margin here flaky.
    sid.tick(255 * ATTACK_PERIODS[0])
    assert v.envelope == 255
    assert v._phase == "decay"

    # decay from 255 to 0x88 (136) never drops below the zone-divisor-1
    # threshold (92), so a flat, generous multiple of the base rate suffices.
    sid.tick(DECAY_RELEASE_PERIODS[0] * 300)
    assert v._phase == "sustain"
    assert v.envelope == v.sustain_level == 0x88

    sid.write_register(voice_offset(0, CR), 0x00)  # gate off -> release
    assert v._phase == "release"
    # a full release crosses every exponential zone (worst case ~x30 near
    # zero); this margin comfortably covers the worst-case total.
    sid.tick(DECAY_RELEASE_PERIODS[0] * 30 * 40)
    assert v.envelope == 0


def test_regate_while_attacking_does_not_reset_envelope_to_zero():
    sid = Sid()
    v = sid.voices[0]
    sid.write_register(voice_offset(0, AD), 0x00)
    sid.write_register(voice_offset(0, CR), GATE)
    for _ in range(ATTACK_PERIODS[0] * 50):
        sid.tick(1)
    level_before = v.envelope
    assert level_before > 0
    sid.write_register(voice_offset(0, CR), GATE)  # re-trigger while still attacking
    assert v.envelope == level_before  # unchanged by the re-trigger itself
    assert v._phase == "attack"


def test_filter_cutoff_and_resonance_registers():
    sid = Sid()
    sid.write_register(FILTER_CUTOFF_LO, 0x07)
    sid.write_register(FILTER_CUTOFF_HI, 0xFF)
    assert sid.cutoff_hz == pytest.approx(12_000.0)
    sid.write_register(FILTER_RES_ROUTE, 0xF0)
    assert sid.resonance_q == pytest.approx(1.0 + 15 * 0.5)


def test_output_sample_is_silent_with_nothing_gated(sid):
    assert sid.output_sample() == 0.0


def test_output_sample_is_nonzero_and_bounded_with_an_active_voice():
    sid = Sid()
    sid.write_register(voice_offset(0, FREQHI), 0x10)
    sid.write_register(voice_offset(0, SR), 0xF0)  # sustain = max, so decay can't pull it back down
    sid.write_register(voice_offset(0, CR), WAVEFORM_SAWTOOTH | GATE)
    sid.write_register(MODE_VOLUME, 0x0F)  # full master volume
    sid.tick(ATTACK_PERIODS[0] * 260)  # comfortably more than the 255 steps needed
    assert sid.voices[0].envelope == 255
    sample = sid.output_sample()
    assert -1.0 <= sample <= 1.0
    assert sample != 0.0


def test_voice_three_disconnect_mutes_it_without_stopping_its_envelope():
    sid = Sid()
    sid.write_register(voice_offset(2, FREQHI), 0x10)
    sid.write_register(voice_offset(2, SR), 0xF0)  # sustain = max
    sid.write_register(voice_offset(2, CR), WAVEFORM_SAWTOOTH | GATE)
    sid.write_register(MODE_VOLUME, 0x8F)  # voice 3 disconnected, full volume
    sid.tick(ATTACK_PERIODS[0] * 260)
    assert sid.voices[2].envelope == 255  # still running
    assert sid.output_sample() == 0.0  # but silent -- only voice 3 was active
