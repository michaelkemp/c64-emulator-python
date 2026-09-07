#!/usr/bin/env python3
"""Boot the staged ROMs, show the VIC-II's screen output in a real
window, and accept real keyboard input.

Phase 8/9: screen + keyboard -- no audio or disk yet (see
docs/roadmap.md's Phases 10-11). Requires this project's `peripherals`
extra: `pip install -e ".[peripherals]"`.

RESTORE is mapped to F12 (see peripherals/keyboard.py -- real hardware
wires it directly to NMI, not through the keyboard matrix).

Usage:
    scripts/stage_roms.sh   # once, if you haven't already
    scripts/run_c64.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pygame

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from c64.machine import Machine  # noqa: E402
from peripherals.keyboard import Keyboard  # noqa: E402
from peripherals.screen import CYCLES_PER_FRAME, Screen  # noqa: E402


def main() -> None:
    roms_dir = REPO_ROOT / "roms" / "c64"
    if not (roms_dir / "kernal").exists():
        raise SystemExit(f"No ROMs staged in {roms_dir}. Run scripts/stage_roms.sh first.")

    machine = Machine.from_roms(roms_dir)  # enable_audio defaults off -- no audio consumer yet (Phase 10)
    screen = Screen(scale=2)
    keyboard = Keyboard(machine.keyboard)

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
                total += machine.step()
            carry = total - CYCLES_PER_FRAME
            screen.draw(machine.vic.render_frame(machine.bus))
            screen.tick()
    finally:
        screen.close()


if __name__ == "__main__":
    main()
