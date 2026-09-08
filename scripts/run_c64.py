#!/usr/bin/env python3
"""Boot the staged ROMs, show the VIC-II's screen output in a real
window, accept real keyboard input, and play real SID audio.

Phase 8/9/10: screen + keyboard + audio -- no disk yet (see
docs/roadmap.md's Phase 11). Requires this project's `peripherals`
extra: `pip install -e ".[peripherals]"`.

RESTORE is mapped to F12 (see peripherals/keyboard.py -- real hardware
wires it directly to NMI, not through the keyboard matrix).

Audio plays through `sounddevice` (PortAudio), not `pygame.mixer` -- see
peripherals/audio.py's module docstring for why: real playback through
pygame's Sound/Channel queueing produced audible artifacts (worst at the
quiet end of each note) that turned out to be inherent to that API, not
a data or timing bug in this project's own code. Pitch is correct
regardless (sample generation is tied to real emulated cycles, not
wall-clock time). Pass --no-audio to skip SID ticking entirely.

Typing a BASIC program reliably: live human keystrokes can be less than
rock solid here (see peripherals/auto_type.py for why). Two
alternatives, both using `AutoTyper`:
  - `--type-file program.bas` types that file's contents automatically
    once boot has settled at the READY prompt.
  - Ctrl+V pastes the real clipboard's text the same reliable way, at
    any point (e.g. once you're already sitting at a prompt).
While `AutoTyper` is busy, this loop fast-forwards -- driving the CPU
directly and skipping the per-step render/audio cost that made an
earlier version of this feature measure at ~1 character/second in
practice (audio briefly off during the burst too, since SID ticking is
the single most expensive part of a step -- see docs/machine.md). Still
not instant on this project's current, unoptimized performance profile,
but a real BASIC program should now take low tens of seconds rather than
minutes. The screen updates periodically (not per keystroke) during a
long paste so it doesn't look frozen, and the window stays responsive to
being closed.

Cartridges: drop a .crt file in cartridge-slot/ (gitignored) and it's
auto-loaded like a real one plugged into the expansion port -- only the
first file found is used. Generic/type-0 cartridges only (plain,
static ROM, no bank-switching registers) -- see docs/cartridge.md for
what that covers and doesn't. Pass --cartridge to load a specific file
instead of scanning the directory.

Usage:
    scripts/stage_roms.sh   # once, if you haven't already
    scripts/run_c64.py
    scripts/run_c64.py --no-audio
    scripts/run_c64.py --type-file examples/sound_test.bas
    scripts/run_c64.py --cartridge cartridge-slot/some_game.crt
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pygame

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from c64.cartridge import Cartridge, UnsupportedCartridge  # noqa: E402
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

# Drop a .crt file in here to have it behave like a real cartridge
# plugged into the expansion port -- gitignored, never committed (see
# docs/cartridge.md). Only the first file found (sorted, so it's
# deterministic) is loaded; if you want a specific one, pass --cartridge
# instead and leave this directory alone or empty.
CARTRIDGE_SLOT_DIR = REPO_ROOT / "cartridge-slot"


def _find_cartridge_in_slot() -> Path | None:
    if not CARTRIDGE_SLOT_DIR.is_dir():
        return None
    candidates = sorted(p for p in CARTRIDGE_SLOT_DIR.iterdir() if p.is_file())
    return candidates[0] if candidates else None

# How often (wall-clock seconds) the fast-forward typing loop checks for
# window-close events and redraws the screen, so a long paste doesn't
# look frozen or become unclosable.
TYPING_UI_CHECK_INTERVAL = 0.1

# With audio enabled, only actually draw the screen every this-many
# frames (CPU/SID stepping and audio generation still happen every
# frame -- only the expensive render_frame()+Screen.draw() call is
# skipped on the rest). Directly measured, not guessed: machine.step()
# for one frame's cycles costs ~12.3ms, render_frame() ~3.7ms, and
# Screen.draw() ~8.2ms -- drawing every frame costs ~24.2ms against a
# 19.95ms real-time budget, a structural ~4.3ms/frame deficit *before*
# any margin at all, which starves AudioOutput's buffer permanently (not
# just during PyPy's initial JIT warm-up -- confirmed by measuring
# `buffered_seconds()` staying pinned near zero for 8+ real seconds with
# drawing enabled every frame, vs. genuinely climbing once it's reduced
# to 1-in-5). 5 gives a real, measured, growing margin with room to
# spare; picked from actual numbers, not tuned to the exact edge. Real
# cost: video refreshes at ~10Hz instead of ~50Hz while audio's on --
# an explicit trade, not hidden. Without audio (SID ticking off), this
# throughput problem doesn't exist (PyPy has much more headroom -- see
# docs/machine.md), so full-rate drawing is left alone in that case.
VIDEO_DRAW_EVERY_WITH_AUDIO = 5


def _dispatch_events(machine, keyboard, auto_typer) -> bool:
    """Drain pending pygame events and apply them; returns False once a
    QUIT is seen. Used by both the normal per-frame loop and the
    fast-forward typing loop's periodic UI check -- the two must handle
    events identically. An earlier version of the fast-forward loop only
    looked for QUIT and silently dropped every other event, including
    KEYUP: a real Ctrl+V's Ctrl-release could land mid-burst and get
    discarded, leaving CTRL "stuck" pressed on the emulated matrix for the
    rest of the burst and corrupting every character AutoTyper typed
    afterwards into a CTRL+<key> combo -- caught from a real screenshot of
    garbled BASIC text, not written correctly the first time."""
    still_running = True
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            still_running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_v and (event.mod & pygame.KMOD_CTRL):
            text = _clipboard_text()
            if text:
                auto_typer.type_text(text)
        else:
            keyboard.handle_event(event, machine)
    return still_running


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
    parser.add_argument(
        "--cartridge",
        type=Path,
        help="load this specific .crt file instead of auto-scanning cartridge-slot/ "
        "(generic/type-0 cartridges only -- see docs/cartridge.md)",
    )
    parser.add_argument(
        "--no-video-draw",
        action="store_true",
        help="skip screen.draw() entirely (but keep screen.tick()'s pacing and the "
        "window/event pump alive) -- diagnostic knob. Under the old pygame.mixer audio "
        "backend this made no difference (that bug was elsewhere -- see "
        "peripherals/audio.py); under the current sounddevice backend, Screen.draw()'s "
        "real per-frame cost genuinely does starve audio (see VIDEO_DRAW_EVERY_WITH_AUDIO "
        "below, which throttles rather than fully disables drawing)",
    )
    args = parser.parse_args()

    roms_dir = REPO_ROOT / "roms" / "c64"
    if not (roms_dir / "kernal").exists():
        raise SystemExit(f"No ROMs staged in {roms_dir}. Run scripts/stage_roms.sh first.")

    program_text = args.type_file.read_text() if args.type_file else None

    cartridge_path = args.cartridge if args.cartridge is not None else _find_cartridge_in_slot()
    cartridge = None
    if cartridge_path is not None:
        try:
            cartridge = Cartridge.from_file(cartridge_path)
            print(f"Cartridge loaded: {cartridge_path.name}" + (f" ({cartridge.name})" if cartridge.name else ""))
        except UnsupportedCartridge as exc:
            print(f"Not loading {cartridge_path.name}: {exc}")

    machine = Machine.from_roms(roms_dir, cartridge=cartridge, enable_audio=not args.no_audio)
    screen = Screen(scale=2)
    keyboard = Keyboard(machine.keyboard)
    auto_typer = AutoTyper(machine.keyboard)
    audio = AudioOutput(machine.sid) if not args.no_audio else None

    carry = 0
    frame_count = 0
    running = True
    try:
        while running:
            running = _dispatch_events(machine, keyboard, auto_typer)

            frame_count += 1
            if program_text is not None and frame_count == BOOT_SETTLE_FRAMES:
                auto_typer.type_text(program_text)

            if auto_typer.busy:
                was_audio_enabled = machine.enable_audio
                machine.enable_audio = False
                last_ui_check = time.perf_counter()
                while auto_typer.busy and running:
                    auto_typer.advance(machine.step())
                    now = time.perf_counter()
                    if now - last_ui_check > TYPING_UI_CHECK_INTERVAL:
                        running = _dispatch_events(machine, keyboard, auto_typer)
                        if not args.no_video_draw:
                            screen.draw(machine.vic.render_frame(machine.bus))
                        screen.tick()
                        last_ui_check = now
                machine.enable_audio = was_audio_enabled
                carry = 0  # resume normal per-frame cadence fresh after the burst
            else:
                total = carry
                while total < CYCLES_PER_FRAME:
                    cycles = machine.step()
                    total += cycles
                    if audio is not None:
                        audio.advance(cycles)
                carry = total - CYCLES_PER_FRAME

            should_draw = not args.no_video_draw and (
                audio is None or frame_count % VIDEO_DRAW_EVERY_WITH_AUDIO == 0
            )
            if should_draw:
                screen.draw(machine.vic.render_frame(machine.bus))
            screen.tick()
    finally:
        if audio is not None:
            audio.close()
        screen.close()


if __name__ == "__main__":
    main()
