#!/usr/bin/env python3
"""Boot the staged ROMs, show the VIC-II's screen output in a real
window, accept real keyboard input, and play real SID audio.

Phase 8/9/10: screen + keyboard + audio -- no disk yet (see
docs/roadmap.md's Phase 11). Requires this project's `peripherals`
extra: `pip install -e ".[peripherals]"`.

RESTORE is mapped to F12 (see peripherals/keyboard.py -- real hardware
wires it directly to NMI, not through the keyboard matrix).

Audio has a real, honest caveat -- see peripherals/audio.py and
docs/machine.md's profiling numbers: this project's unoptimized
pure-Python core runs slower than real time once SID ticking is enabled,
so sustained playback may have audible gaps under load. Pitch itself is
still correct (sample generation is tied to real emulated cycles, not
wall-clock time). Pass --no-audio to skip SID ticking entirely and get
the Phase 8/9 behavior back if the gaps bother you more than the sound
is worth.

Usage:
    scripts/stage_roms.sh   # once, if you haven't already
    scripts/run_c64.py
    scripts/run_c64.py --no-audio
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pygame

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from c64.machine import Machine  # noqa: E402
from peripherals.audio import AudioOutput  # noqa: E402
from peripherals.keyboard import Keyboard  # noqa: E402
from peripherals.screen import CYCLES_PER_FRAME, Screen  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-audio", action="store_true", help="skip SID ticking entirely")
    args = parser.parse_args()

    roms_dir = REPO_ROOT / "roms" / "c64"
    if not (roms_dir / "kernal").exists():
        raise SystemExit(f"No ROMs staged in {roms_dir}. Run scripts/stage_roms.sh first.")

    machine = Machine.from_roms(roms_dir, enable_audio=not args.no_audio)
    screen = Screen(scale=2)
    keyboard = Keyboard(machine.keyboard)
    audio = AudioOutput(machine.sid) if not args.no_audio else None

    carry = 0
    running = True
    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                else:
                    keyboard.handle_event(event, machine)
            total = carry
            while total < CYCLES_PER_FRAME:
                cycles = machine.step()
                total += cycles
                if audio is not None:
                    audio.advance(cycles)
            carry = total - CYCLES_PER_FRAME
            screen.draw(machine.vic.render_frame(machine.bus))
            screen.tick()
    finally:
        if audio is not None:
            audio.close()
        screen.close()


if __name__ == "__main__":
    main()
