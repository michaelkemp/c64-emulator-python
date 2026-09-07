"""The C64's 8x8 keyboard matrix, wired across CIA1's two ports.

See docs/cia.md's "Keyboard matrix and joysticks" section: this models
the matrix electrically (which raw row/column coordinates are shorted
together when a key is held). `KEY_POSITIONS` -- the symbolic name ->
(row, col) table -- was verified empirically against this project's own
staged, real KERNAL (Phase 9), not trusted from either of two disputed
community references; see docs/cia.md for exactly how and what it caught.

Real hardware wires the matrix symmetrically between CIA1's Port A and
Port B, so scanning works in either direction (drive rows on A, sense
columns on B -- the KERNAL's own convention -- or the reverse, which a
handful of programs use). `sense_columns`/`sense_rows` reflect that.

`RESTORE` isn't here -- real hardware wires it directly to the CPU's NMI
line, not through CIA1 like every other key. See docs/cia.md.
"""

from __future__ import annotations

# Verified against the real KERNAL's own GETIN routine, one position at a
# time -- see docs/cia.md. Digits/letters use their own character;
# everything else gets a descriptive name.
KEY_POSITIONS: dict[str, tuple[int, int]] = {
    "DEL": (0, 0), "RETURN": (0, 1), "CRSR_RIGHT": (0, 2), "F7": (0, 3),
    "F1": (0, 4), "F3": (0, 5), "F5": (0, 6), "CRSR_DOWN": (0, 7),
    "3": (1, 0), "W": (1, 1), "A": (1, 2), "4": (1, 3),
    "Z": (1, 4), "S": (1, 5), "E": (1, 6), "LSHIFT": (1, 7),
    "5": (2, 0), "R": (2, 1), "D": (2, 2), "6": (2, 3),
    "C": (2, 4), "F": (2, 5), "T": (2, 6), "X": (2, 7),
    "7": (3, 0), "Y": (3, 1), "G": (3, 2), "8": (3, 3),
    "B": (3, 4), "H": (3, 5), "U": (3, 6), "V": (3, 7),
    "9": (4, 0), "I": (4, 1), "J": (4, 2), "0": (4, 3),
    "M": (4, 4), "K": (4, 5), "O": (4, 6), "N": (4, 7),
    "PLUS": (5, 0), "P": (5, 1), "L": (5, 2), "MINUS": (5, 3),
    "PERIOD": (5, 4), "COLON": (5, 5), "AT": (5, 6), "COMMA": (5, 7),
    "POUND": (6, 0), "ASTERISK": (6, 1), "SEMICOLON": (6, 2), "HOME": (6, 3),
    "RSHIFT": (6, 4), "EQUALS": (6, 5), "UP_ARROW": (6, 6), "SLASH": (6, 7),
    "1": (7, 0), "LEFT_ARROW": (7, 1), "COMMODORE": (7, 2), "2": (7, 3),
    "SPACE": (7, 4), "CTRL": (7, 5), "Q": (7, 6), "RUN_STOP": (7, 7),
}


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

    def press_key(self, name: str) -> None:
        self.press(*KEY_POSITIONS[name])

    def release_key(self, name: str) -> None:
        self.release(*KEY_POSITIONS[name])

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
