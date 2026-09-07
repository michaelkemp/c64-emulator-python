import pytest

from c64.vic_ii import (
    BACKGROUND_COLOR0,
    BORDER_COLOR,
    BORDER_X,
    BORDER_Y,
    COLLISION_SPRITE_BG,
    COLLISION_SPRITE_SPRITE,
    CONTROL1,
    CONTROL2,
    IRQ_ENABLE,
    IRQ_STATUS,
    MEMORY_POINTERS,
    RASTER,
    VicII,
)


class FakeBus:
    def __init__(self):
        self.mem = {}
        self.color_ram = {}

    def read_vic(self, address):
        return self.mem.get(address, 0)

    def read_color_nibble(self, index):
        return self.color_ram.get(index, 0)


@pytest.fixture
def vic():
    return VicII()


def test_border_and_background_colors_mask_to_a_nibble(vic):
    vic.write_register(BORDER_COLOR, 0xFE)
    vic.write_register(BACKGROUND_COLOR0, 0xF3)
    assert vic.border_color == 0x0E
    assert vic.background_color == 0x03


def test_memory_pointers_compute_matrix_and_char_base(vic):
    vic.write_register(MEMORY_POINTERS, 0x12)  # VM=0001, CB=001
    assert vic.video_matrix_base == 0x0400
    assert vic.char_base == 0x0800


def test_control1_rst8_is_separate_on_read_vs_write(vic):
    vic.write_register(CONTROL1, 0x80)  # sets raster COMPARE's high bit
    assert vic.raster_compare == 0x100

    vic.current_raster = 0x150
    assert vic.read_register(CONTROL1) & 0x80  # reflects current line's high bit
    assert vic.raster_compare == 0x100  # unaffected by current_raster changing


def test_irq_status_is_write_one_to_clear_not_read_to_clear(vic):
    vic._irq_flags = 0x01
    assert vic.read_register(IRQ_STATUS) & 0x01
    assert vic.read_register(IRQ_STATUS) & 0x01  # still set: reading doesn't clear
    vic.write_register(IRQ_STATUS, 0x00)  # writing 0 doesn't clear either
    assert vic.read_register(IRQ_STATUS) & 0x01
    vic.write_register(IRQ_STATUS, 0x01)  # writing 1 to the bit clears it
    assert vic.read_register(IRQ_STATUS) & 0x01 == 0


def test_irq_status_upper_bits_always_read_as_one(vic):
    assert vic.read_register(IRQ_STATUS) & 0x70 == 0x70


def test_irq_enable_only_keeps_the_bottom_four_bits(vic):
    vic.write_register(IRQ_ENABLE, 0xFF)
    assert vic.read_register(IRQ_ENABLE) == 0xFF  # top nibble forced to 1 anyway
    vic._irq_flags = 0x01
    assert vic.irq_line is True
    vic.write_register(IRQ_ENABLE, 0x00)
    assert vic.irq_line is False


def test_collision_registers_are_always_zero_and_read_only(vic):
    vic.write_register(COLLISION_SPRITE_SPRITE, 0xFF)
    vic.write_register(COLLISION_SPRITE_BG, 0xFF)
    assert vic.read_register(COLLISION_SPRITE_SPRITE) == 0x00
    assert vic.read_register(COLLISION_SPRITE_BG) == 0x00


def test_unconnected_registers_are_open_bus(vic):
    vic.write_register(0x2F, 0x55)
    assert vic.read_register(0x2F) == 0xFF
    assert vic.read_register(0x3F) == 0xFF


def test_step_line_wraps_and_fires_raster_irq_on_match(vic):
    vic.write_register(RASTER, 2)  # compare = line 2
    vic.step_line()
    assert vic.current_raster == 1
    assert vic.read_register(IRQ_STATUS) & 0x01 == 0
    vic.step_line()
    assert vic.current_raster == 2
    assert vic.read_register(IRQ_STATUS) & 0x01


def test_render_frame_fills_border_and_draws_one_character(vic):
    bus = FakeBus()
    vic.write_register(MEMORY_POINTERS, 0x12)  # matrix @ $0400, chars @ $0800
    vic.write_register(BORDER_COLOR, 14)
    vic.write_register(BACKGROUND_COLOR0, 6)
    vic.write_register(CONTROL1, 0x10 | 0x08)  # DEN=1, RSEL=1 (25 rows)
    vic.write_register(CONTROL2, 0x08)  # CSEL=1 (40 cols)

    bus.mem[0x0400] = 65  # screen code 65 at row 0, col 0
    bus.mem[0x0800 + 65 * 8 + 0] = 0xFF  # first pixel row of that char: all set
    bus.color_ram[0] = 5

    frame = vic.render_frame(bus)

    assert frame[0][0] == 14  # top-left corner is border
    for x in range(BORDER_X, BORDER_X + 8):
        assert frame[BORDER_Y][x] == 5  # char's first pixel row: foreground
    for x in range(BORDER_X, BORDER_X + 8):
        assert frame[BORDER_Y + 1][x] == 6  # second pixel row: char data is 0 -> background


def test_display_disabled_shows_background_only(vic):
    bus = FakeBus()
    vic.write_register(MEMORY_POINTERS, 0x12)
    vic.write_register(BACKGROUND_COLOR0, 6)
    vic.write_register(CONTROL1, 0x00)  # DEN=0

    bus.mem[0x0400] = 65
    bus.mem[0x0800 + 65 * 8] = 0xFF
    bus.color_ram[0] = 5

    frame = vic.render_frame(bus)
    assert frame[BORDER_Y][BORDER_X] == 6  # background, not the character's foreground
