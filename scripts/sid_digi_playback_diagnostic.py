#!/usr/bin/env python3
"""Render SID "digi-playback" (rapid $D418/master-volume rewrites, used by
some real C64 music/SFX routines as crude 4-bit PCM) through this
project's Sid model, as actual WAV files to listen to.

See docs/sid.md's "digi-playback untested" gap and
docs/vice-gap-analysis.md's recommended cheap verification test: "feed a
synthetic volume-register ramp through output_sample() and listen/
measure". tests/c64/test_sid_digi_playback.py has the numeric assertions
this is built from; this script is the "listen" half.

Sid.output_sample() applies MODE_VOLUME as one clean linear multiply on
the whole mixed signal -- that distinguishes two different real digi-
playback techniques, rendered as two separate files here:

  --with-baseline (default): voice 1 is frozen at a constant nonzero
    level (the TEST bit forces its accumulator, and so its waveform
    output, to 0 -- triangle at accumulator=0 is 0, the bottom of its
    bipolar range once DC-centered) with its envelope held at full
    sustain, then $D418's volume nibble is swept 0..15..0 on a repeating
    ramp. This is the "ride an already-playing tone" technique; a linear
    volume multiply should reproduce it as an audible buzz at the ramp
    rate.
  --no-baseline: the same volume ramp, but with no voice active at all --
    the "purer" real technique some digi-tunes use, riding the SID's own
    analog DC leakage with no oscillator running. This project's model
    has no such leakage (a true-zero signal times any volume is still
    zero), so this should render as silence -- itself the useful finding,
    not a bug to fix blindly.

Usage:
    scripts/sid_digi_playback_diagnostic.py                  # digi_playback_baseline.wav
    scripts/sid_digi_playback_diagnostic.py --no-baseline     # digi_playback_silent.wav
"""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from c64.sid import AD, CR, GATE, MODE_VOLUME, SR, TEST, VOICE_STRIDE, WAVEFORM_TRIANGLE, Sid  # noqa: E402
from c64.vic_ii import PAL_CLOCK_HZ  # noqa: E402


def render(with_baseline: bool, seconds: float, ramp_hz: float, sample_rate: int) -> list[float]:
    sid = Sid(sample_rate=sample_rate)

    if with_baseline:
        sid.write_register(0 * VOICE_STRIDE + AD, 0x00)  # attack=0 (fastest, ~2ms)
        sid.write_register(0 * VOICE_STRIDE + SR, 0xF0)  # sustain=max, release=0
        sid.write_register(0 * VOICE_STRIDE + CR, GATE | TEST | WAVEFORM_TRIANGLE)
        # Let the envelope fully attack (and settle into sustain) before the
        # volume ramp starts, so the baseline is stable throughout.
        sid.tick(round(0.05 * PAL_CLOCK_HZ))

    cycles_per_sample = PAL_CLOCK_HZ / sample_rate
    cycles_per_ramp_step = PAL_CLOCK_HZ / (ramp_hz * 16)  # 16 volume steps per ramp cycle

    accumulated_sample = 0.0
    accumulated_ramp = 0.0
    volume = 0
    samples = []
    for _ in range(int(sample_rate * seconds)):
        accumulated_sample += cycles_per_sample
        whole = int(accumulated_sample)
        accumulated_sample -= whole

        accumulated_ramp += whole
        while accumulated_ramp >= cycles_per_ramp_step:
            accumulated_ramp -= cycles_per_ramp_step
            volume = (volume + 1) % 16
            sid.write_register(MODE_VOLUME, volume)

        sid.tick(whole)
        samples.append(sid.output_sample())
    return samples


def write_wav(path: Path, samples: list[float], sample_rate: int) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for s in samples:
            value = max(-32768, min(32767, round(s * 32767)))
            frames += value.to_bytes(2, "little", signed=True)
        wav.writeframes(bytes(frames))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--no-baseline", action="store_true",
        help="test the 'pure' silence-only DC-leakage technique instead",
    )
    parser.add_argument("--seconds", type=float, default=1.0)
    parser.add_argument("--ramp-hz", type=float, default=110.0, help="16-step volume ramp repeats per second")
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    with_baseline = not args.no_baseline
    out = args.out or REPO_ROOT / ("digi_playback_baseline.wav" if with_baseline else "digi_playback_silent.wav")

    samples = render(with_baseline, args.seconds, args.ramp_hz, args.sample_rate)
    write_wav(out, samples, args.sample_rate)
    peak = max(abs(s) for s in samples)
    note = " (silence, as expected -- see this script's module docstring)" if peak == 0.0 else ""
    print(f"Wrote {out} ({args.seconds}s, {args.ramp_hz}Hz ramp, {'with' if with_baseline else 'no'} baseline voice)")
    print(f"Peak sample magnitude: {peak:.4f}{note}")


if __name__ == "__main__":
    main()
