#!/usr/bin/env python3
"""Minimal pygame audio test with **zero** dependency on this project's
own SID/Machine/AudioOutput code -- generates a sine wave and a triangle
wave directly with plain Python math, and plays each as a single
`pygame.mixer.Sound` with one `.play()` call each (no chunking, no
queueing, none of `AudioOutput`'s machinery at all).

Why this exists: if this project's own SID-generated audio sounds wrong
(noisy, shapeless, clicking) but this script's independently-generated
tones sound clean through the same pygame/speakers, that isolates the
problem to this project's own code (`Sid`/`AudioOutput`). If *this*
script *also* sounds wrong, the problem is this machine's pygame/SDL
audio setup itself, unrelated to anything in this project.

Usage:
    python3 scripts/pygame_tone_test.py
"""

from __future__ import annotations

import array
import math
import time

import pygame

SAMPLE_RATE = 44100
FREQ_HZ = 440.0
DURATION_S = 2.0
AMPLITUDE = 0.5  # fraction of full scale -- avoids clipping


def sine_wave(freq: float, duration_s: float, sample_rate: int) -> list[int]:
    n = int(duration_s * sample_rate)
    return [
        round(32767 * AMPLITUDE * math.sin(2 * math.pi * freq * i / sample_rate))
        for i in range(n)
    ]


def triangle_wave(freq: float, duration_s: float, sample_rate: int) -> list[int]:
    """A plain, textbook triangle wave -- ramps linearly -1..+1..-1 each
    cycle. Not SID's own triangle generator, deliberately: this is a
    from-scratch reference waveform, independent of any of this
    project's own code, for pygame to reproduce."""
    n = int(duration_s * sample_rate)
    period_samples = sample_rate / freq
    out = []
    for i in range(n):
        phase = (i % period_samples) / period_samples  # 0.0 .. 1.0
        value = 4 * abs(phase - 0.5) - 1  # triangle centered on 0, range -1..1
        out.append(round(32767 * AMPLITUDE * value))
    return out


def play(samples: list[int], label: str) -> None:
    print(f"Playing {label} ({len(samples)} samples, {len(samples) / SAMPLE_RATE:.1f}s)...")
    buf = array.array("h", samples)
    sound = pygame.mixer.Sound(buffer=buf.tobytes())
    sound.play()
    time.sleep(len(samples) / SAMPLE_RATE + 0.3)


def main() -> None:
    pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1)
    try:
        play(sine_wave(FREQ_HZ, DURATION_S, SAMPLE_RATE), f"{FREQ_HZ:.0f}Hz sine wave")
        time.sleep(0.5)
        play(triangle_wave(FREQ_HZ, DURATION_S, SAMPLE_RATE), f"{FREQ_HZ:.0f}Hz triangle wave")
    finally:
        pygame.mixer.quit()


if __name__ == "__main__":
    main()
