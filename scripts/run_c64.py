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

Typing a BASIC program reliably: live human keystrokes can be less than
rock solid here (see peripherals/auto_type.py for why -- the short
version: this main loop only drains keyboard events once per simulated
video frame, so a fast enough real keypress can land entirely within one
frame and never reach the emulated KERNAL). Two alternatives, both using
`AutoTyper` to type at a fixed, simulated-frame pace instead:
  - `--type-file program.bas` types that file's contents automatically
    once boot has settled at the READY prompt.
  - Ctrl+V pastes the real clipboard's text the same reliable way, at
    any point (e.g. once you're already sitting at a prompt).

Usage:
    scripts/stage_roms.sh   # once, if you haven't already
    scripts/run_c64.py
    scripts/run_c64.py --no-audio
    scripts/run_c64.py --type-file examples/sound_test.bas
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
from peripherals.auto_type import AutoTyper  # noqa: E402
from peripherals.keyboard import Keyboard  # noqa: E402
from peripherals.screen import CYCLES_PER_FRAME, Screen  # noqa: E402

# Comfortably more than the ~107 frames boot has taken in practice (RAM
# test + hardware init before BASIC reaches its keyboard-wait loop -- see
# docs/roadmap.md's Phase 4/7 notes) -- how long --type-file waits before
# it starts, so keystrokes don't land during boot and go unseen.
BOOT_SETTLE_FRAMES = 150


def _clipboard_text() -> str | None:
    """Best-effort real clipboard read (X11/Windows/macOS via SDL) --
    returns None if unavailable or empty, never raises."""
    try:
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        for mime in pygame.scrap.get_types():
            if mime.startswith("text/plain"):
                data = pygame.scrap.get(mime)
                if data:
                    return data.decode("utf-8", errors="replace").rstrip("\x00")
    except Exception:
        return None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-audio", action="store_true", help="skip SID ticking entirely")
    parser.add_argument("--type-file", type=Path, help="type this file's contents in once booted")
    args = parser.parse_args()

    roms_dir = REPO_ROOT / "roms" / "c64"
    if not (roms_dir / "kernal").exists():
        raise SystemExit(f"No ROMs staged in {roms_dir}. Run scripts/stage_roms.sh first.")

    program_text = args.type_file.read_text() if args.type_file else None

    machine = Machine.from_roms(roms_dir, enable_audio=not args.no_audio)
    screen = Screen(scale=2)
    keyboard = Keyboard(machine.keyboard)
    auto_typer = AutoTyper(machine.keyboard)
    audio = AudioOutput(machine.sid) if not args.no_audio else None

    carry = 0
    frame_count = 0
    running = True
    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_v and (event.mod & pygame.KMOD_CTRL):
                    text = _clipboard_text()
                    if text:
                        auto_typer.type_text(text)
                else:
                    keyboard.handle_event(event, machine)

            total = carry
            while total < CYCLES_PER_FRAME:
                cycles = machine.step()
                total += cycles
                if audio is not None:
                    audio.advance(cycles)
            carry = total - CYCLES_PER_FRAME

            frame_count += 1
            if program_text is not None and frame_count == BOOT_SETTLE_FRAMES:
                auto_typer.type_text(program_text)
            auto_typer.pump()

            screen.draw(machine.vic.render_frame(machine.bus))
            screen.tick()
    finally:
        if audio is not None:
            audio.close()
        screen.close()


if __name__ == "__main__":
    main()
