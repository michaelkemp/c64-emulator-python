"""The C64's 8x8 keyboard matrix, wired across CIA1's two ports.

See docs/cia.md's "Keyboard matrix and joysticks" section: this models
the matrix electrically (which raw row/column coordinates are shorted
together when a key is held), not symbolically -- there's deliberately no
key-name table here yet, since two community references for the real
row/column assignment disagree with each other and this project hasn't
verified either against the real KERNAL ROM's own table yet.

Real hardware wires the matrix symmetrically between CIA1's Port A and
Port B, so scanning works in either direction (drive rows on A, sense
columns on B -- the KERNAL's own convention -- or the reverse, which a
handful of programs use). `sense_columns`/`sense_rows` reflect that.
"""

from __future__ import annotations


class KeyboardMatrix:
    def __init__(self) -> None:
        self._pressed: set[tuple[int, int]] = set()

    def press(self, row: int, col: int) -> None:
        self._pressed.add((row, col))

    def release(self, row: int, col: int) -> None:
        self._pressed.discard((row, col))

    def is_pressed(self, row: int, col: int) -> bool:
        return (row, col) in self._pressed

    def release_all(self) -> None:
        self._pressed.clear()

    def sense_columns(self, rows_driven_low: int) -> int:
        """Column bits pulled low by a pressed key on any of the given
        (bitmask) driven-low rows."""
        pulled = 0
        for row in range(8):
            if not (rows_driven_low >> row) & 1:
                continue
            for col in range(8):
                if (row, col) in self._pressed:
                    pulled |= 1 << col
        return pulled

    def sense_rows(self, columns_driven_low: int) -> int:
        """The reverse of `sense_columns`, for scanning in the other
        direction."""
        pulled = 0
        for col in range(8):
            if not (columns_driven_low >> col) & 1:
                continue
            for row in range(8):
                if (row, col) in self._pressed:
                    pulled |= 1 << row
        return pulled


class Cia1Ports:
    """CIA1's `port_coupler`: the keyboard matrix plus up to two
    joysticks, combined -- see docs/cia.md. Joystick 2 shares Port A with
    the keyboard's row-select lines; joystick 1 shares Port B with the
    column-sense lines, exactly as on real hardware (and with the same
    real-hardware caveat: moving a joystick can look like a keypress to
    software that isn't scanning the keyboard carefully)."""

    def __init__(self, keyboard: KeyboardMatrix, *, joystick_port1=None, joystick_port2=None) -> None:
        self.keyboard = keyboard
        self.joystick_port1 = joystick_port1
        self.joystick_port2 = joystick_port2

    def sense_a(self, b_driven_low: int) -> int:
        pulled = self.keyboard.sense_rows(b_driven_low)
        if self.joystick_port2 is not None:
            pulled |= self.joystick_port2.pulldown_mask()
        return pulled

    def sense_b(self, a_driven_low: int) -> int:
        pulled = self.keyboard.sense_columns(a_driven_low)
        if self.joystick_port1 is not None:
            pulled |= self.joystick_port1.pulldown_mask()
        return pulled
