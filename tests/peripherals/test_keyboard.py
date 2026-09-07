import pytest

pygame = pytest.importorskip("pygame")

from c64.keyboard_matrix import KEY_POSITIONS, KeyboardMatrix  # noqa: E402
from peripherals.keyboard import Keyboard  # noqa: E402


class FakeCpu:
    def __init__(self):
        self.nmi_count = 0

    def nmi(self):
        self.nmi_count += 1


class FakeMachine:
    def __init__(self):
        self.cpu = FakeCpu()


def down(key):
    return pygame.event.Event(pygame.KEYDOWN, key=key)


def up(key):
    return pygame.event.Event(pygame.KEYUP, key=key)


@pytest.fixture
def kb():
    matrix = KeyboardMatrix()
    return Keyboard(matrix), matrix


def test_plain_letter_key_maps_to_the_matrix(kb):
    keyboard, matrix = kb
    keyboard.handle_event(down(pygame.K_a))
    assert matrix.is_pressed(*KEY_POSITIONS["A"])
    keyboard.handle_event(up(pygame.K_a))
    assert not matrix.is_pressed(*KEY_POSITIONS["A"])


def test_real_shift_key_maps_to_lshift(kb):
    keyboard, matrix = kb
    keyboard.handle_event(down(pygame.K_LSHIFT))
    assert matrix.is_pressed(*KEY_POSITIONS["LSHIFT"])
    keyboard.handle_event(up(pygame.K_LSHIFT))
    assert not matrix.is_pressed(*KEY_POSITIONS["LSHIFT"])


def test_left_arrow_presses_crsr_right_and_synthesizes_shift(kb):
    keyboard, matrix = kb
    keyboard.handle_event(down(pygame.K_LEFT))
    assert matrix.is_pressed(*KEY_POSITIONS["CRSR_RIGHT"])
    assert matrix.is_pressed(*KEY_POSITIONS["LSHIFT"])
    keyboard.handle_event(up(pygame.K_LEFT))
    assert not matrix.is_pressed(*KEY_POSITIONS["CRSR_RIGHT"])
    assert not matrix.is_pressed(*KEY_POSITIONS["LSHIFT"])


def test_up_arrow_presses_crsr_down_and_synthesizes_shift(kb):
    keyboard, matrix = kb
    keyboard.handle_event(down(pygame.K_UP))
    assert matrix.is_pressed(*KEY_POSITIONS["CRSR_DOWN"])
    assert matrix.is_pressed(*KEY_POSITIONS["LSHIFT"])
    keyboard.handle_event(up(pygame.K_UP))
    assert not matrix.is_pressed(*KEY_POSITIONS["LSHIFT"])


def test_releasing_one_arrow_does_not_release_a_still_held_real_shift(kb):
    keyboard, matrix = kb
    keyboard.handle_event(down(pygame.K_LSHIFT))  # user is genuinely holding shift
    keyboard.handle_event(down(pygame.K_LEFT))
    keyboard.handle_event(up(pygame.K_LEFT))
    assert matrix.is_pressed(*KEY_POSITIONS["LSHIFT"])  # still held -- real shift wants it
    keyboard.handle_event(up(pygame.K_LSHIFT))
    assert not matrix.is_pressed(*KEY_POSITIONS["LSHIFT"])


def test_releasing_one_arrow_does_not_release_shift_the_other_arrow_still_needs(kb):
    keyboard, matrix = kb
    keyboard.handle_event(down(pygame.K_LEFT))
    keyboard.handle_event(down(pygame.K_UP))
    keyboard.handle_event(up(pygame.K_LEFT))
    assert matrix.is_pressed(*KEY_POSITIONS["LSHIFT"])  # up-arrow still needs it
    keyboard.handle_event(up(pygame.K_UP))
    assert not matrix.is_pressed(*KEY_POSITIONS["LSHIFT"])


def test_restore_key_triggers_nmi_on_the_machine():
    matrix = KeyboardMatrix()
    keyboard = Keyboard(matrix)
    machine = FakeMachine()
    keyboard.handle_event(down(pygame.K_F12), machine)
    assert machine.cpu.nmi_count == 1


def test_unmapped_key_is_ignored_without_error(kb):
    keyboard, matrix = kb
    keyboard.handle_event(down(pygame.K_F2))  # not in KEY_MAP
    assert True  # just must not raise
