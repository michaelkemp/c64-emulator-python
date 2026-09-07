from c64.joystick import Joystick


def test_no_direction_pressed_is_zero_mask():
    assert Joystick().pulldown_mask() == 0


def test_each_direction_and_fire_set_their_own_bit():
    joy = Joystick()
    joy.up = True
    joy.fire = True
    assert joy.pulldown_mask() == 0x01 | 0x10


def test_all_directions_at_once():
    joy = Joystick()
    joy.up = joy.down = joy.left = joy.right = joy.fire = True
    assert joy.pulldown_mask() == 0x1F
