#!/usr/bin/env python3
"""Boot the staged ROMs and show the VIC-II's screen output in a real
window.

Phase 8: screen output only -- no keyboard, audio, or disk yet (see
docs/roadmap.md's Phases 9-11). Requires this project's `peripherals`
extra: `pip install -e ".[peripherals]"`.

Usage:
    scripts/stage_roms.sh   # once, if you haven't already
    scripts/run_c64.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from c64.machine import Machine  # noqa: E402
from peripherals.screen import CYCLES_PER_FRAME, Screen  # noqa: E402


def main() -> None:
    roms_dir = REPO_ROOT / "roms" / "c64"
    if not (roms_dir / "kernal").exists():
        raise SystemExit(f"No ROMs staged in {roms_dir}. Run scripts/stage_roms.sh first.")

    machine = Machine.from_roms(roms_dir)
    screen = Screen(scale=2)

    carry = 0
    running = True
    try:
        while running:
            running = screen.poll_events()
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
