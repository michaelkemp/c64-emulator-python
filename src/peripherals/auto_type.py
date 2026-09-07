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
KERNAL's keyboard scan. Measured empirically (not guessed) against the
real KERNAL's own `GETIN` routine: a key held for as few as ~6000 PHI2
cycles (roughly a third of one video frame's worth) already registers
reliably, and gaps as short as ~2000-4000 cycles are enough to
distinguish a released-then-repressed *same* key from one held
continuously -- with some quantization noise near the low end from
aligning with the KERNAL's own ~17000-cycle scan period. `HOLD_CYCLES`/
`GAP_CYCLES` below use a safety margin above those measured minimums,
verified against real multi-character sequences including same-key
repeats ("AABBCC", "ABABAB"). `advance(cycles)` replaces `pump()`,
matching this project's established `tick(cycles)` shape
(`CIA6526`/`VicII`/`AudioOutput`) -- callers drive it with the same
cycle count `Machine.step()` returns, and critically should do so in a
tight loop *without* paying per-step render/audio/event costs while
`busy` (see `scripts/run_c64.py`), which is where the real speedup comes
from -- not from cutting the hold/gap durations alone.

Covers what a simple BASIC test program needs: letters, digits, space,
RETURN, and common punctuation -- including the shifted symbols
(`"`, `(`, `)`, `!`, `&`, `'`, `<`, `>`, `?`), verified empirically the
same way `KeyboardMatrix.KEY_POSITIONS` was (see docs/cia.md), not
guessed.
"""

from __future__ import annotations

from c64.keyboard_matrix import KeyboardMatrix

# Empirically measured minimums (see module docstring): hold >=6000,
# gap >=2000-4000 with some quantization noise near the low end. These
# use a comfortable safety margin above that, verified against real
# multi-character sequences via the KERNAL's own GETIN routine.
HOLD_CYCLES = 8_000
GAP_CYCLES = 20_000

# Verified empirically, the same way as KEY_POSITIONS: SHIFT + this key
# produces these on real hardware.
_SHIFTED = {
    '"': "2", "(": "8", ")": "9", "!": "1", "&": "6", "'": "7",
    "<": "COMMA", ">": "PERIOD", "?": "SLASH",
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
