import pytest

pygame = pytest.importorskip("pygame")

from c64.joystick import Joystick  # noqa: E402
from peripherals.joystick_input import JoystickInput  # noqa: E402


def down(key):
    return pygame.event.Event(pygame.KEYDOWN, key=key)


def up(key):
    return pygame.event.Event(pygame.KEYUP, key=key)


@pytest.fixture
def ji():
    j1, j2 = Joystick(), Joystick()
    return JoystickInput(j1, j2), j1, j2


def test_defaults_to_port_2(ji):
    joystick_input, j1, j2 = ji
    assert joystick_input.active_port == 2
    assert joystick_input.joystick is j2


def test_cardinal_direction_keys(ji):
    joystick_input, j1, j2 = ji
    joystick_input.handle_event(down(pygame.K_KP8))
    assert j2.up is True
    joystick_input.handle_event(up(pygame.K_KP8))
    assert j2.up is False


def test_fire_key(ji):
    joystick_input, j1, j2 = ji
    joystick_input.handle_event(down(pygame.K_KP0))
    assert j2.fire is True
    joystick_input.handle_event(up(pygame.K_KP0))
    assert j2.fire is False


def test_diagonal_key_asserts_two_directions(ji):
    joystick_input, j1, j2 = ji
    joystick_input.handle_event(down(pygame.K_KP7))  # up-left
    assert (j2.up, j2.left) == (True, True)
    joystick_input.handle_event(up(pygame.K_KP7))
    assert (j2.up, j2.left) == (False, False)


def test_overlapping_diagonal_and_cardinal_release_independently(ji):
    """Holding both KP7 (up+left) and KP8 (up), then releasing KP7,
    must leave "up" asserted -- it's still held via KP8. Mirrors
    peripherals/keyboard.py's reference-counted LSHIFT pattern."""
    joystick_input, j1, j2 = ji
    joystick_input.handle_event(down(pygame.K_KP7))
    joystick_input.handle_event(down(pygame.K_KP8))
    assert (j2.up, j2.left) == (True, True)

    joystick_input.handle_event(up(pygame.K_KP7))
    assert (j2.up, j2.left) == (True, False)  # up still held via KP8

    joystick_input.handle_event(up(pygame.K_KP8))
    assert (j2.up, j2.left) == (False, False)


def test_f2_switches_active_port(ji):
    joystick_input, j1, j2 = ji
    joystick_input.handle_event(down(pygame.K_F2))
    assert joystick_input.active_port == 1
    assert joystick_input.joystick is j1

    joystick_input.handle_event(down(pygame.K_F2))
    assert joystick_input.active_port == 2
    assert joystick_input.joystick is j2


def test_switching_port_releases_everything_on_the_old_one(ji):
    joystick_input, j1, j2 = ji
    joystick_input.handle_event(down(pygame.K_KP8))  # up, on port 2
    joystick_input.handle_event(down(pygame.K_KP0))  # fire, on port 2
    assert (j2.up, j2.fire) == (True, True)

    joystick_input.handle_event(down(pygame.K_F2))  # switch to port 1

    assert (j2.up, j2.fire) == (False, False)  # released on the outgoing port
    assert (j1.up, j1.fire) == (False, False)  # nothing pressed for port 1 either


def test_unmapped_key_is_ignored(ji):
    joystick_input, j1, j2 = ji
    joystick_input.handle_event(down(pygame.K_a))  # no exception, no effect
    assert (j2.up, j2.down, j2.left, j2.right, j2.fire) == (False, False, False, False, False)
