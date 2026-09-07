#!/usr/bin/env python3
"""Play a short test tone through the real CPU+Bus+SID stack and save it
as a WAV file.

Reproduces the manual check used to validate Phase 6 (see docs/sid.md,
docs/roadmap.md): a tiny genuine 6502 program, assembled with this
project's own ported assembler, pokes a real SID voice's frequency,
waveform, and gate directly -- then Sid.tick()/output_sample() generate
real audio samples from that state, exactly the way scripts/render_frame.py
renders a real video frame.

Unlike the boot screen, there's no real Commodore ROM content that plays
a tune on its own, so this is a synthetic single-note demo, not "real
software" -- it exists to prove the SID pipeline (register pokes -> real
CPU execution -> oscillator/envelope/filter -> audio samples) actually
works end to end, the same role render_frame.py's boot screen played for
the VIC-II.

No audio library dependency (this project has none at runtime -- see
CLAUDE.md): WAV encoding uses the standard library's `wave` module.

Usage:
    scripts/render_audio.py                      # writes c64_tone.wav, 440Hz
    scripts/render_audio.py --freq 261.63 --seconds 2 --out c.wav
"""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from c6502.asm import assemble  # noqa: E402
from c6502.emulator.cpu import CPU  # noqa: E402
from c64.bus import Bus  # noqa: E402
from c64.sid import Sid  # noqa: E402
from c64.vic_ii import PAL_CLOCK_HZ  # noqa: E402

WAVEFORM_TRIANGLE = 0x10
GATE = 0x01


def play_note(freq_hz: float, seconds: float, sample_rate: int) -> list[float]:
    freq_reg = round(freq_hz * (1 << 24) / PAL_CLOCK_HZ)
    lo, hi = freq_reg & 0xFF, (freq_reg >> 8) & 0xFF

    source = f"""
        .org $0810
    start:
        LDA #${lo:02X}
        STA $D400       ; voice 1 frequency, low byte
        LDA #${hi:02X}
        STA $D401       ; voice 1 frequency, high byte
        LDA #$F0
        STA $D406       ; sustain = max (holds the note at full volume)
        LDA #${WAVEFORM_TRIANGLE | GATE:02X}
        STA $D404       ; triangle waveform, gate on
        LDA #$0F
        STA $D418       ; master volume = max
    loop:
        JMP loop
        .org $FFFC
        .word start
    """

    image = assemble(source)
    sid = Sid(sample_rate=sample_rate)
    bus = Bus(sid=sid)
    bus.load(image.origin, image.data)
    cpu = CPU(bus)
    cpu.reset()

    for _ in range(10):  # the 5 LDA/STA pairs, stop before the JMP loop
        cpu.step()

    cycles_per_sample = PAL_CLOCK_HZ / sample_rate
    accumulated = 0.0
    samples = []
    for _ in range(int(sample_rate * seconds)):
        accumulated += cycles_per_sample
        whole = int(accumulated)
        accumulated -= whole
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freq", type=float, default=440.0, help="note frequency in Hz")
    parser.add_argument("--seconds", type=float, default=1.0)
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "c64_tone.wav")
    args = parser.parse_args()

    samples = play_note(args.freq, args.seconds, args.sample_rate)
    write_wav(args.out, samples, args.sample_rate)
    print(f"Wrote {args.out} ({args.seconds}s @ {args.freq}Hz, {args.sample_rate}Hz sample rate)")


if __name__ == "__main__":
    main()
