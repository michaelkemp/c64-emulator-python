"""End-to-end regression test: `AutoTyper` driven through the real
staged ROMs and the actual interrupt-driven KERNAL keyboard scan --
not a synthetic `KeyboardMatrix` in isolation (see test_auto_type.py for
those, which can't observe this class of bug at all since they never
run interrupts).

Why this exists: an earlier `HOLD_CYCLES`/`GAP_CYCLES` pair was
"verified" against a harness that called the KERNAL's `GETIN` routine
directly, bypassing the real interrupt-driven scan+debounce loop
entirely. That harness looked reliable but wasn't representative --
real hardware scans the keyboard and debounces once per jiffy IRQ
(driven by CIA1 Timer A, ~16,421 PHI2 cycles), and a key held for less
than one full period can land entirely between two scans and never be
seen. This shipped, and was only caught when the user ran
`--type-file examples/sprite_test.bas` for real and got back a screen
full of dropped characters and `?SYNTAX ERROR`s. This test reproduces
that exact scenario (boot the real ROMs, drive `Machine` + `AutoTyper`
the same way `run_c64.py` does, verify nothing got dropped) so it can't
regress silently again.

Skipped if ROMs aren't staged locally -- same convention as the Dormann
suite's GPLv3 fixture (see scripts/stage_roms.sh).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from c64.machine import Machine
from peripherals.auto_type import AutoTyper
from peripherals.screen import CYCLES_PER_FRAME

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROMS_DIR = REPO_ROOT / "roms" / "c64"
BOOT_SETTLE_FRAMES = 150  # see scripts/run_c64.py


def _run_frames(machine: Machine, count: int) -> None:
    for _ in range(count):
        total = 0
        while total < CYCLES_PER_FRAME:
            total += machine.step()


def _type(machine: Machine, auto_typer: AutoTyper, text: str) -> None:
    auto_typer.type_text(text)
    while auto_typer.busy:
        auto_typer.advance(machine.step())


def _boot() -> Machine:
    machine = Machine.from_roms(ROMS_DIR, enable_audio=False)
    _run_frames(machine, BOOT_SETTLE_FRAMES)
    return machine


def _screen_code_to_ascii(code: int) -> str:
    # Real C64 screen-code layout: $00-$1A is '@' + A-Z (offset -0x40 from
    # ASCII), $20-$3F matches ASCII directly (space through '?', which is
    # everything examples/sprite_test.bas actually uses).
    if 0x00 <= code <= 0x1A:
        return chr(code + 0x40)
    if 0x20 <= code <= 0x3F:
        return chr(code)
    return "�"


def _read_screen_text(machine: Machine) -> str:
    lines = []
    for row in range(25):
        row_bytes = (machine.bus.read8(0x0400 + row * 40 + col) for col in range(40))
        lines.append("".join(_screen_code_to_ascii(b) for b in row_bytes).rstrip())
    return "\n".join(lines)


def _skip_without_roms() -> None:
    if not (ROMS_DIR / "kernal").exists():
        pytest.skip("No ROMs staged -- run scripts/stage_roms.sh first.")


def test_a_short_line_is_entered_with_no_characters_dropped():
    _skip_without_roms()
    machine = _boot()
    auto_typer = AutoTyper(machine.keyboard)

    _type(machine, auto_typer, "HELLO\n")
    _run_frames(machine, 10)

    lines = _read_screen_text(machine).splitlines()
    # BASIC echoes the typed line verbatim before evaluating it -- a
    # dropped character (the original bug) would show up as e.g. "EO"
    # instead of "HELLO" on its own line.
    assert any(line.strip() == "HELLO" for line in lines)


@pytest.mark.slow
def test_a_real_multiline_program_is_entered_and_lists_back_clean():
    _skip_without_roms()
    machine = _boot()
    auto_typer = AutoTyper(machine.keyboard)

    source = (REPO_ROOT / "examples" / "sprite_test.bas").read_text()
    _type(machine, auto_typer, source)
    _run_frames(machine, 5)
    _type(machine, auto_typer, "LIST\n")
    _run_frames(machine, 40)

    text = _read_screen_text(machine)
    # Any dropped/corrupted character in a real line number or BASIC
    # keyword makes real BASIC reject that line immediately with its own
    # ?SYNTAX ERROR at entry time -- a clean listing with none anywhere
    # is exactly what "every character survived" looks like.
    assert "SYNTAX" not in text
