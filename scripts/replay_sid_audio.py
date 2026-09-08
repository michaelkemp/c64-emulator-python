#!/usr/bin/env python3
"""Diagnostic: generate a program's SID audio completely headlessly
(no real-time constraint, no video, no keyboard -- just boot, type,
RUN, and record every sample `Sid.output_sample()` produces), then
replay *only* that pre-generated audio afterwards through the real
`AudioOutput` (sounddevice) playback path, with nothing else competing
for CPU time.

Why this exists: originally built to isolate whether "sounds like
noise" was caused by `pygame.mixer`'s chunked-delivery mechanism itself
or by `run_c64.py`'s combined real-time loop not keeping up. It turned
out to be neither -- see `peripherals/audio.py`'s module docstring for
the actual cause (an artifact inherent to `pygame.mixer.Channel`
queueing, fixed by switching to `sounddevice` entirely). Kept as a
useful sanity check: if a known-good, headlessly-generated sample
stream ever sounds wrong played back through `AudioOutput` alone, that
isolates the problem to `AudioOutput`/`sounddevice`, not to `Sid` or to
`Machine`'s real-time loop.

Usage:
    python3 scripts/replay_sid_audio.py examples/sound_test.bas
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from c64.machine import Machine  # noqa: E402
from c64.sid import Sid  # noqa: E402
from c64.vic_ii import PAL_CLOCK_HZ  # noqa: E402
from peripherals.audio import AudioOutput  # noqa: E402
from peripherals.auto_type import AutoTyper  # noqa: E402
from peripherals.screen import CYCLES_PER_FRAME  # noqa: E402

BOOT_SETTLE_FRAMES = 150
SAMPLE_RATE = 44100


def generate_headless(program_path: Path, run_seconds: float) -> list[float]:
    """Boot, type the program, RUN it, and record every raw SID sample
    (as floats, straight from `Sid.output_sample()`) as fast as this
    process can go -- no pacing, no video, no keyboard."""
    machine = Machine.from_roms(REPO_ROOT / "roms" / "c64", enable_audio=True)
    for _ in range(BOOT_SETTLE_FRAMES):
        total = 0
        while total < CYCLES_PER_FRAME:
            total += machine.step()

    auto_typer = AutoTyper(machine.keyboard)
    auto_typer.type_text(program_path.read_text())
    while auto_typer.busy:
        auto_typer.advance(machine.step())
    auto_typer.type_text("RUN\n")
    while auto_typer.busy:
        auto_typer.advance(machine.step())

    cycles_per_sample = PAL_CLOCK_HZ / SAMPLE_RATE
    acc = 0.0
    samples: list[float] = []
    target_samples = int(SAMPLE_RATE * run_seconds)
    while len(samples) < target_samples:
        cycles = machine.step()
        acc += cycles
        while acc >= cycles_per_sample:
            acc -= cycles_per_sample
            samples.append(machine.sid.output_sample())
    return samples


def replay(samples: list[float]) -> None:
    """Play pre-generated samples through the real `AudioOutput` --
    the *only* thing this process is doing, at real wall-clock pacing,
    by re-ticking a fresh `Sid` fed from a lookup table so `advance()`
    sees exactly the recorded samples in order."""
    sid = Sid(sample_rate=SAMPLE_RATE)
    index = [0]
    original_output_sample = sid.output_sample

    def replay_output_sample() -> float:
        i = index[0]
        index[0] += 1
        return samples[i] if i < len(samples) else 0.0

    sid.output_sample = replay_output_sample  # type: ignore[method-assign]
    audio = AudioOutput(sid, sample_rate=SAMPLE_RATE)

    duration = len(samples) / SAMPLE_RATE
    print(f"Replaying {len(samples)} samples ({duration:.1f}s of audio)...")
    cycles_per_sample = PAL_CLOCK_HZ / SAMPLE_RATE
    cycles_per_step = int(cycles_per_sample * 100)  # feed in small bursts, like Machine.step() does
    total_cycles_needed = int(cycles_per_sample * len(samples))

    next_deadline = time.perf_counter()
    fed = 0
    while fed < total_cycles_needed:
        step = min(cycles_per_step, total_cycles_needed - fed)
        audio.advance(step)
        fed += step
        next_deadline += step / PAL_CLOCK_HZ
        sleep_for = next_deadline - time.perf_counter()
        if sleep_for > 0:
            time.sleep(sleep_for)

    time.sleep(0.2)  # let the last bit finish playing
    sid.output_sample = original_output_sample  # type: ignore[method-assign]
    audio.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("program", type=Path, help="BASIC program to type and RUN")
    parser.add_argument("--seconds", type=float, default=8.0, help="how many seconds of audio to generate")
    args = parser.parse_args()

    print("Generating audio headlessly (no video, no real-time pacing)...")
    samples = generate_headless(args.program, args.seconds)
    print(f"Generated {len(samples)} samples ({len(samples) / SAMPLE_RATE:.1f}s).")
    replay(samples)


if __name__ == "__main__":
    main()
