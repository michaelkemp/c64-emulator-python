"""A single digital joystick: up/down/left/right/fire, active low.

Wired to bits 0-4 of whichever CIA1 port its port is plugged into (see
`keyboard_matrix.py`'s `Cia1Ports`) -- these are the same physical pins
the keyboard matrix uses, which is why a joystick can be misread as
keypresses on real hardware too (not modeled as a conflict here; the two
sources' pulldowns are just OR'd together, per docs/cia.md).
"""

from __future__ import annotations

UP, DOWN, LEFT, RIGHT, FIRE = 0x01, 0x02, 0x04, 0x08, 0x10


class Joystick:
    def __init__(self) -> None:
        self.up = False
        self.down = False
        self.left = False
        self.right = False
        self.fire = False

    def pulldown_mask(self) -> int:
        mask = 0
        if self.up:
            mask |= UP
        if self.down:
            mask |= DOWN
        if self.left:
            mask |= LEFT
        if self.right:
            mask |= RIGHT
        if self.fire:
            mask |= FIRE
        return mask
