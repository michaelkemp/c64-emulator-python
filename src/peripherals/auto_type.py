"""Reliable programmatic text entry into `KeyboardMatrix`, timed in
simulated video frames rather than wall-clock time.

Why this exists: driving `KeyboardMatrix` from real pygame KEYDOWN/KEYUP
events (`keyboard.py`) works for live human typing, but the main loop
(`scripts/run_c64.py`) only drains the event queue once per simulated
video frame -- a real keypress fast enough that its down *and* up both
land within one frame's wall-clock duration (which can be tens of
milliseconds on this project's current, unoptimized performance profile
-- see `docs/machine.md`) nets out to a press the emulated KERNAL never
actually sees. `AutoTyper` sidesteps this entirely by holding each key
for a fixed number of *simulated* frames, decoupled from host speed or
real typing speed -- the same technique this project's own validation
scripts (e.g. Phase 9's "type HELLO" check) already used by hand.

Covers what a simple BASIC test program needs: letters, digits, space,
RETURN, and common punctuation -- including the shifted symbols
(`"`, `(`, `)`, `!`, `&`, `'`, `<`, `>`, `?`), verified empirically the
same way `KeyboardMatrix.KEY_POSITIONS` was (see docs/cia.md), not
guessed. An earlier version of this table omitted `<`/`>`/`?` entirely;
they were silently dropped from typed text rather than raising, which is
by design for genuinely unmappable characters (a stray Unicode curly
quote from a paste shouldn't abort the whole thing) -- but for `<`/`>`
specifically it silently corrupted real BASIC (`IF X<24` typed as
`IF X24`), caught by actually running the typed program, not just
inspecting the mapping table.
"""

from __future__ import annotations

from c64.keyboard_matrix import KeyboardMatrix

HOLD_FRAMES = 4
GAP_FRAMES = 2

# Verified empirically (Phase "quick BASIC input" session), the same way
# as KEY_POSITIONS: SHIFT + this key produces these on real hardware.
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
        """Queue text to be typed; does not block -- call `pump()` once
        per simulated frame to actually advance it."""
        self._queue.extend(text)

    @property
    def busy(self) -> bool:
        return bool(self._queue) or self._phase != "idle"

    def pump(self) -> None:
        """Advance by exactly one simulated video frame."""
        if self._phase == "holding":
            self._counter += 1
            if self._counter >= HOLD_FRAMES:
                for name in self._held:
                    self.keyboard.release_key(name)
                self._held = []
                self._phase = "gap"
                self._counter = 0
            return
        if self._phase == "gap":
            self._counter += 1
            if self._counter >= GAP_FRAMES:
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
