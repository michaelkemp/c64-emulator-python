"""Real numeric-keypad input -> one C64 `Joystick` port at a time, via
pygame key events.

Requires this project's `peripherals` extra.

Most real C64 software reads only one joystick port -- conventionally
port 2 (CIA1 Port A, $DC00; see `keyboard_matrix.py`'s `Cia1Ports`),
which is why single-joystick games default to reading it. Since this
project doesn't dedicate a real second input device to each port, the
numpad drives *one* port at a time, defaulting to port 2, switchable at
runtime with F2 (an otherwise-unmapped key -- see peripherals/
keyboard.py's KEY_MAP, which only wires up F1/F3/F5/F7).

Numpad layout (the standard "numpad as 8-way digital joystick" keyset
most C64 emulators default to):

      7   8   9        up-left    up    up-right
      4       6        left             right
      1   2   3        down-left  down  down-right
          0            fire

Diagonals assert two direction bits at once, exactly like a real
digital joystick's own microswitches do -- reference-counted per
direction (not a single flag), the same pattern peripherals/keyboard.py
already uses for its synthesized LSHIFT: holding both KP7 (up+left) and
KP8 (up), then releasing just KP7, must leave "up" still asserted.
"""

from __future__ import annotations

import pygame

from c64.joystick import Joystick

# numpad key -> the direction attribute(s) it asserts on `Joystick` while held.
DIRECTION_KEYS: dict[int, tuple[str, ...]] = {
    pygame.K_KP8: ("up",),
    pygame.K_KP2: ("down",),
    pygame.K_KP4: ("left",),
    pygame.K_KP6: ("right",),
    pygame.K_KP7: ("up", "left"),
    pygame.K_KP9: ("up", "right"),
    pygame.K_KP1: ("down", "left"),
    pygame.K_KP3: ("down", "right"),
}
FIRE_KEY = pygame.K_KP0
PORT_SWITCH_KEY = pygame.K_F2

_DIRECTIONS = ("up", "down", "left", "right")


class JoystickInput:
    def __init__(self, joystick1: Joystick, joystick2: Joystick) -> None:
        self._ports = {1: joystick1, 2: joystick2}
        self.active_port = 2  # port 2 is the real-world single-joystick default
        # Which held keys currently assert each direction -- reference-
        # counted so overlapping diagonal + cardinal keys release cleanly
        # (see module docstring).
        self._direction_sources: dict[str, set[int]] = {d: set() for d in _DIRECTIONS}

    @property
    def joystick(self) -> Joystick:
        return self._ports[self.active_port]

    def handle_event(self, event) -> None:
        if event.type == pygame.KEYDOWN:
            self._key_down(event.key)
        elif event.type == pygame.KEYUP:
            self._key_up(event.key)

    def _key_down(self, key: int) -> None:
        if key == PORT_SWITCH_KEY:
            self._switch_port()
            return
        if key == FIRE_KEY:
            self.joystick.fire = True
            return
        for direction in DIRECTION_KEYS.get(key, ()):
            was_idle = not self._direction_sources[direction]
            self._direction_sources[direction].add(key)
            if was_idle:
                setattr(self.joystick, direction, True)

    def _key_up(self, key: int) -> None:
        if key == FIRE_KEY:
            self.joystick.fire = False
            return
        for direction in DIRECTION_KEYS.get(key, ()):
            self._direction_sources[direction].discard(key)
            if not self._direction_sources[direction]:
                setattr(self.joystick, direction, False)

    def _switch_port(self) -> None:
        # Release everything on the outgoing port first -- otherwise a
        # direction/fire still held across the switch would stay stuck
        # on a port no key is being pressed for anymore.
        joystick = self.joystick
        joystick.up = joystick.down = joystick.left = joystick.right = False
        joystick.fire = False
        for sources in self._direction_sources.values():
            sources.clear()
        self.active_port = 2 if self.active_port == 1 else 1
        print(f"Joystick input now driving port {self.active_port}")
