"""Diagnostic tests for whether SID "digi-playback" (rapid $D418
master-volume rewrites used as crude 4-bit PCM by some real C64 music/SFX
routines) works through this project's Sid model -- see docs/sid.md's
"digi-playback untested" gap and docs/vice-gap-analysis.md's recommended
cheap verification test: "feed a synthetic volume-register ramp through
output_sample() and listen/measure".

Sid.output_sample() applies MODE_VOLUME as one clean linear multiply on
the whole mixed signal (see sid.py). That distinguishes two different
real-hardware digi-playback techniques, tested separately below:
  - riding an already-playing tone (a nonzero baseline signal, amplitude-
    modulated by the volume nibble) -- a linear multiply reproduces this
    fine.
  - riding the SID's own analog DC leakage with *no* oscillator running
    at all -- impossible for a linear model (zero times any volume is
    still zero), so this is a genuine, disclosed gap, not a bug.

scripts/sid_digi_playback_diagnostic.py renders both scenarios to actual
WAV files to listen to, not just measure numerically.
"""

from c64.sid import AD, CR, GATE, MODE_VOLUME, SR, TEST, VOICE_STRIDE, WAVEFORM_TRIANGLE, Sid
from c64.vic_ii import PAL_CLOCK_HZ


def _hold_voice0_at_full_sustain_with_frozen_accumulator(sid: Sid) -> None:
    """A real, documented C64 technique: TEST+a waveform freezes that
    voice's oscillator at accumulator=0 (triangle's output there is 0,
    the very bottom of its bipolar range once DC-centered) while GATE
    still drives its envelope up normally -- giving a stable, nonzero
    baseline signal to modulate."""
    sid.write_register(0 * VOICE_STRIDE + AD, 0x00)  # attack=0 (fastest, ~2ms)
    sid.write_register(0 * VOICE_STRIDE + SR, 0xF0)  # sustain=max, release=0
    sid.write_register(0 * VOICE_STRIDE + CR, GATE | TEST | WAVEFORM_TRIANGLE)
    sid.tick(round(0.05 * PAL_CLOCK_HZ))  # comfortably more than attack+decay need


def test_digi_playback_modulates_a_held_background_baseline():
    """With a stable nonzero baseline held, sweeping $D418's volume
    nibble alone should produce 16 distinct, evenly-spaced output levels
    -- the "riding an existing tone" technique, reproduced correctly by
    this model's linear volume multiply."""
    sid = Sid()
    _hold_voice0_at_full_sustain_with_frozen_accumulator(sid)

    levels = []
    for volume in range(16):
        sid.write_register(MODE_VOLUME, volume)
        levels.append(sid.output_sample())

    assert len(set(levels)) == 16, "expected 16 distinct output levels, one per volume nibble value"
    assert levels[0] == 0.0  # volume 0 is always silence

    diffs = [round(levels[i + 1] - levels[i], 6) for i in range(15)]
    assert len(set(diffs)) == 1, f"expected evenly spaced steps, got {diffs}"


def test_digi_playback_is_silent_with_no_active_voice():
    """The "purer" real-hardware technique some digi-tunes use rides the
    SID's own analog DC leakage with no oscillator running at all -- this
    model has no such leakage (a true-zero signal times any volume is
    still zero), so this specific variant cannot work here. A disclosed
    gap to know about, not a bug to chase blindly."""
    sid = Sid()

    levels = []
    for volume in range(16):
        sid.write_register(MODE_VOLUME, volume)
        levels.append(sid.output_sample())

    assert all(level == 0.0 for level in levels)
