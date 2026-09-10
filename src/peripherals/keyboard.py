"""Real keyboard input -> `KeyboardMatrix`, via pygame key events.

Requires this project's `peripherals` extra (`pip install -e
".[peripherals]"`).

Most PC keys map to a single C64 matrix position. The four cursor keys
are the exception: real hardware has only two physical keys for all four
directions (`CRSR_RIGHT`/`CRSR_DOWN`), with `SHIFT` reversing the
direction (held = left/up, released = right/down). To give a modern
keyboard's four separate arrow keys their expected individual behavior,
Left/Up press the matrix position *and* synthesize an `LSHIFT` press for
as long as that arrow key is held. `LSHIFT` is reference-counted (which
sources are currently asserting it -- the real key, and/or either arrow),
not a single flag: releasing one arrow key must not force-release a real
Shift the user is still physically holding (or the other arrow key still
needs).

`RESTORE` isn't a matrix key on real hardware (see docs/cia.md) -- it's
mapped here directly to `Machine.cpu.nmi()`, edge-triggered on press,
matching how `Machine.step()` already treats CIA2's NMI output.

The real C64's `*` is its own dedicated, unshifted key (top-right of the
QWERTY row, between `@`/`↑`) -- not a Shift+8 combo (real hardware's own
Shift+8 is `(`, and this project deliberately keeps that mapping rather
than repurposing it). A standard PC keyboard has no equivalent dedicated
key, so the numeric keypad's `*` (`K_KP_MULTIPLY`) is used instead --
safe alongside `JoystickInput`, which only claims the numpad's *digit*
keys (0-9) for directions/fire, never its operator keys (`*`/`/`/`-`/`+`).
"""

from __future__ import annotations

import pygame

from c64.keyboard_matrix import KeyboardMatrix

# PC key -> C64 matrix position name. Alphanumerics and punctuation map
# directly; a few PC-only keys are given the closest real C64 equivalent.
KEY_MAP: dict[int, str] = {
    pygame.K_a: "A", pygame.K_b: "B", pygame.K_c: "C", pygame.K_d: "D",
    pygame.K_e: "E", pygame.K_f: "F", pygame.K_g: "G", pygame.K_h: "H",
    pygame.K_i: "I", pygame.K_j: "J", pygame.K_k: "K", pygame.K_l: "L",
    pygame.K_m: "M", pygame.K_n: "N", pygame.K_o: "O", pygame.K_p: "P",
    pygame.K_q: "Q", pygame.K_r: "R", pygame.K_s: "S", pygame.K_t: "T",
    pygame.K_u: "U", pygame.K_v: "V", pygame.K_w: "W", pygame.K_x: "X",
    pygame.K_y: "Y", pygame.K_z: "Z",
    pygame.K_0: "0", pygame.K_1: "1", pygame.K_2: "2", pygame.K_3: "3",
    pygame.K_4: "4", pygame.K_5: "5", pygame.K_6: "6", pygame.K_7: "7",
    pygame.K_8: "8", pygame.K_9: "9",
    pygame.K_RETURN: "RETURN", pygame.K_SPACE: "SPACE",
    pygame.K_BACKSPACE: "DEL", pygame.K_DELETE: "DEL",
    pygame.K_HOME: "HOME", pygame.K_ESCAPE: "RUN_STOP",
    pygame.K_LCTRL: "CTRL", pygame.K_RCTRL: "CTRL",
    pygame.K_RSHIFT: "RSHIFT",  # LSHIFT is handled specially -- see Keyboard
    pygame.K_LALT: "COMMODORE", pygame.K_RALT: "COMMODORE",
    pygame.K_F1: "F1", pygame.K_F3: "F3", pygame.K_F5: "F5", pygame.K_F7: "F7",
    pygame.K_PLUS: "PLUS", pygame.K_KP_PLUS: "PLUS",
    pygame.K_MINUS: "MINUS", pygame.K_KP_MINUS: "MINUS",
    pygame.K_PERIOD: "PERIOD", pygame.K_COMMA: "COMMA",
    pygame.K_COLON: "COLON", pygame.K_SEMICOLON: "SEMICOLON",
    pygame.K_AT: "AT", pygame.K_EQUALS: "EQUALS",
    pygame.K_SLASH: "SLASH", pygame.K_BACKSLASH: "POUND",
    pygame.K_ASTERISK: "ASTERISK", pygame.K_KP_MULTIPLY: "ASTERISK",
    pygame.K_RIGHT: "CRSR_RIGHT", pygame.K_DOWN: "CRSR_DOWN",
}

# Arrow keys needing a synthesized LSHIFT to reverse direction, and which
# matrix position each one presses.
_SHIFTED_ARROWS = {
    pygame.K_LEFT: "CRSR_RIGHT",
    pygame.K_UP: "CRSR_DOWN",
}


_REAL_LSHIFT = object()  # sentinel source, distinct from any pygame keycode


class Keyboard:
    def __init__(self, matrix: KeyboardMatrix) -> None:
        self.matrix = matrix
        # Which sources currently want LSHIFT asserted: the real LSHIFT
        # key and/or either synthesizing arrow key. Reference-counted via
        # this set, not a single flag -- see module docstring.
        self._lshift_sources: set[object] = set()

    def handle_event(self, event, machine=None) -> None:
        if event.type == pygame.KEYDOWN:
            self._key_down(event.key, machine)
        elif event.type == pygame.KEYUP:
            self._key_up(event.key)

    def _assert_lshift(self, source: object) -> None:
        was_idle = not self._lshift_sources
        self._lshift_sources.add(source)
        if was_idle:
            self.matrix.press_key("LSHIFT")

    def _deassert_lshift(self, source: object) -> None:
        self._lshift_sources.discard(source)
        if not self._lshift_sources:
            self.matrix.release_key("LSHIFT")

    def _key_down(self, key: int, machine) -> None:
        if key == pygame.K_LSHIFT:
            self._assert_lshift(_REAL_LSHIFT)
            return
        if key in _SHIFTED_ARROWS:
            self.matrix.press_key(_SHIFTED_ARROWS[key])
            self._assert_lshift(key)
            return
        name = KEY_MAP.get(key)
        if name is not None:
            self.matrix.press_key(name)
            return
        if key in (pygame.K_PAUSE, pygame.K_F12):  # RESTORE
            if machine is not None:
                machine.cpu.nmi()

    def _key_up(self, key: int) -> None:
        if key == pygame.K_LSHIFT:
            self._deassert_lshift(_REAL_LSHIFT)
            return
        if key in _SHIFTED_ARROWS:
            self.matrix.release_key(_SHIFTED_ARROWS[key])
            self._deassert_lshift(key)
            return
        name = KEY_MAP.get(key)
        if name is not None:
            self.matrix.release_key(name)
