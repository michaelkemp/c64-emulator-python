from c64.joystick import Joystick
from c64.keyboard_matrix import Cia1Ports, KeyboardMatrix


def test_sense_columns_reports_pressed_keys_on_driven_rows():
    kb = KeyboardMatrix()
    kb.press(row=2, col=5)
    kb.press(row=3, col=0)

    # only row 2 driven low -> only column 5 should show pulled low
    assert kb.sense_columns(rows_driven_low=0b0000_0100) == 1 << 5
    # neither row driven -> nothing sensed
    assert kb.sense_columns(rows_driven_low=0b0000_0000) == 0
    # both rows driven -> both columns show
    assert kb.sense_columns(rows_driven_low=0b0000_1100) == (1 << 5) | (1 << 0)


def test_sensing_is_symmetric_in_both_directions():
    kb = KeyboardMatrix()
    kb.press(row=1, col=6)
    assert kb.sense_columns(rows_driven_low=1 << 1) == 1 << 6
    assert kb.sense_rows(columns_driven_low=1 << 6) == 1 << 1


def test_release_clears_a_key():
    kb = KeyboardMatrix()
    kb.press(4, 4)
    assert kb.is_pressed(4, 4)
    kb.release(4, 4)
    assert not kb.is_pressed(4, 4)
    assert kb.sense_columns(0xFF) == 0


def test_cia1_ports_combines_keyboard_and_joysticks():
    kb = KeyboardMatrix()
    kb.press(row=0, col=0)
    joy1 = Joystick()
    joy1.fire = True
    joy2 = Joystick()
    joy2.up = True

    ports = Cia1Ports(kb, joystick_port1=joy1, joystick_port2=joy2)

    # port B senses: keyboard columns for driven row 0, plus joystick 1's fire bit
    assert ports.sense_b(a_driven_low=0b0000_0001) == (1 << 0) | 0x10
    # port A senses: joystick 2's up bit (no rows driven low here)
    assert ports.sense_a(b_driven_low=0x00) == 0x01
