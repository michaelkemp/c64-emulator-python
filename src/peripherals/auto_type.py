"""Reliable programmatic text entry into `KeyboardMatrix`, timed in real
emulated PHI2 cycles rather than wall-clock time or simulated frames.

Why this exists: driving `KeyboardMatrix` from real pygame KEYDOWN/KEYUP
events (`keyboard.py`) works for live human typing, but the main loop
(`scripts/run_c64.py`) only drains the event queue once per simulated
video frame -- a real keypress fast enough that its down *and* up both
land within one frame's wall-clock duration nets out to a press the
emulated KERNAL never actually sees. `AutoTyper` sidesteps this by
holding each key for a fixed number of PHI2 cycles -- reliable
regardless of real typing speed.

**Revision history worth knowing about**: the first version of this
timed itself in simulated *video frames* (`pump()`, no argument, called
once per iteration of `run_c64.py`'s main loop) at 4 hold + 2 gap frames
per character. That's reliable but was measured at ~1 character per
second in practice -- because each "frame" in that loop pays the full
cost of CPU+chip emulation *and* screen rendering *and* audio generation
*and* event polling, not just the minimum needed to satisfy the real
KERNAL's keyboard scan. `advance(cycles)` replaces `pump()`, matching
this project's established `tick(cycles)` shape (`CIA6526`/`VicII`/
`AudioOutput`) -- callers drive it with the same cycle count
`Machine.step()` returns, and critically should do so in a tight loop
*without* paying per-step render/audio/event costs while `busy` (see
`scripts/run_c64.py`), which is where the real speedup comes from.

**The hold/gap cycle counts were wrong once, in a way that shipped**:
an earlier revision set `HOLD_CYCLES = 8_000` / `GAP_CYCLES = 20_000`,
"verified" against the real KERNAL's `GETIN` routine called directly in
a standalone test harness. That harness was misleading -- it didn't
drive the real machine's interrupt-driven keyboard scan the way normal
execution does, so it couldn't have caught the actual failure mode.
Real hardware (and this emulator, correctly) scans the keyboard matrix
and runs its debounce logic once per jiffy IRQ, driven by CIA1 Timer A
-- confirmed here by reading back `$DC04`/`$DC05` after boot, which
shows a period of ~16,421 PHI2 cycles (~60Hz at the PAL clock). A key
held for *less* than one full IRQ period can land entirely between two
scans and never be seen at all; `HOLD_CYCLES = 8_000` was well under
half of that. This wasn't a hypothetical -- the user ran
`--type-file examples/sprite_test.bas` and got back a screen full of
dropped characters and `?SYNTAX ERROR`s, reproduced exactly with a
headless script driving `Machine` + `AutoTyper` the same way
`run_c64.py` does. Swept hold/gap values against that same real,
booted-ROM harness (not the misleading `GETIN`-only one): both values
need to comfortably clear the ~16,421-cycle IRQ period -- `16_421`
itself was still marginal (dropped a character in a plain "HELLO"),
`17_000` was clean, and `20_000`/`20_000` reproduced the *exact* real
`examples/sprite_test.bas` file with zero corruption end-to-end
(typed the whole program, then `LIST`ed it back with no `?SYNTAX
ERROR` anywhere). `HOLD_CYCLES`/`GAP_CYCLES` below use that verified
value, not the old broken one -- see
`tests/peripherals/test_auto_type_integration.py`, which actually boots
the real staged ROMs and types a real multi-line program end-to-end,
unlike `test_auto_type.py`'s `KeyboardMatrix`-in-isolation tests, which
can't observe this class of bug at all since they never run interrupts.

Covers what a simple BASIC test program needs: letters, digits, space,
RETURN, and common punctuation -- including the shifted symbols
(`"`, `(`, `)`, `!`, `&`, `'`, `<`, `>`, `?`, `#`, `$`, `%`), verified
empirically the same way `KeyboardMatrix.KEY_POSITIONS` was (see
docs/cia.md), not guessed. `#`/`$`/`%` (SHIFT+3/4/5) were the last gap in
this pattern -- found the same way `<`/`>`/`?` were: a real BASIC program
(this one using a string array, `DIM WN$(...)`) got silently corrupted
(`$` dropped entirely, turning a string array into a numeric one --
`?TYPE MISMATCH ERROR` the moment it tried to store a string into it) by
actually running it through the real KERNAL, not by inspecting the
mapping table.
"""

from __future__ import annotations

from c64.keyboard_matrix import KeyboardMatrix

# Verified against the real, booted KERNAL's interrupt-driven keyboard
# scan (see module docstring) -- both must comfortably clear CIA1 Timer
# A's ~16,421-cycle jiffy IRQ period, or a held key can land entirely
# between two scans and be dropped. 20,000 reproduced the real
# examples/sprite_test.bas file with zero corruption end-to-end.
HOLD_CYCLES = 20_000
GAP_CYCLES = 20_000

# Verified empirically, the same way as KEY_POSITIONS: SHIFT + this key
# produces these on real hardware.
_SHIFTED = {
    '"': "2", "(": "8", ")": "9", "!": "1", "&": "6", "'": "7",
    "<": "COMMA", ">": "PERIOD", "?": "SLASH",
    "#": "3", "$": "4", "%": "5",
}
_DIRECT = {
    " ": "SPACE", "\n": "RETURN", "\r": "RETURN",
    ":": "COLON", ";": "SEMICOLON", ",": "COMMA", ".": "PERIOD",
    "+": "PLUS", "-": "MINUS", "=": "EQUALS", "*": "ASTERISK",
    "/": "SLASH", "@": "AT",
}


def _keys_for_char(ch: str) -> list[str] | None:
    if ch in _SHIFTED:
        return ["LSHIFT", _SHIFTED[ch]]
    if ch in _DIRECT:
        return [_DIRECT[ch]]
    if ch.isalpha() and len(ch) == 1:
        return [ch.upper()]
    if ch.isdigit():
        return [ch]
    return None


class AutoTyper:
    def __init__(self, keyboard: KeyboardMatrix) -> None:
        self.keyboard = keyboard
        self._queue: list[str] = []
        self._phase = "idle"  # "idle" | "holding" | "gap"
        self._counter = 0
        self._held: list[str] = []

    def type_text(self, text: str) -> None:
        """Queue text to be typed; does not block -- call `advance()`
        with real elapsed cycles to actually advance it."""
        self._queue.extend(text)

    @property
    def busy(self) -> bool:
        return bool(self._queue) or self._phase != "idle"

    def advance(self, cycles: int) -> None:
        """Feed in the cycle count from a `Machine.step()` call -- same
        shape as `CIA6526.tick`/`VicII.tick`/`AudioOutput.advance`."""
        if self._phase == "holding":
            self._counter += cycles
            if self._counter >= HOLD_CYCLES:
                for name in self._held:
                    self.keyboard.release_key(name)
                self._held = []
                self._phase = "gap"
                self._counter = 0
            return
        if self._phase == "gap":
            self._counter += cycles
            if self._counter >= GAP_CYCLES:
                self._phase = "idle"
                self._counter = 0
            return
        if not self._queue:
            return
        names = _keys_for_char(self._queue.pop(0))
        if names is None:
            return
        self._held = names
        for name in names:
            self.keyboard.press_key(name)
        self._phase = "holding"
        self._counter = 0
