import pytest

from c64.vic_ii import (
    BACKGROUND_COLOR0,
    BADLINE_FIRST_LINE,
    BADLINE_LAST_LINE,
    BORDER_COLOR,
    BORDER_X,
    BORDER_Y,
    CYCLES_PER_LINE,
    COLLISION_SPRITE_BG,
    COLLISION_SPRITE_SPRITE,
    CONTROL1,
    CONTROL2,
    DEN_LATCH_LINE,
    DISPLAY_HEIGHT,
    IRQ_ENABLE,
    IRQ_STATUS,
    MEMORY_POINTERS,
    MSBX,
    RASTER,
    SPRITE_COLOR_BASE,
    SPRITE_ENABLE,
    SPRITE_MULTICOLOR0,
    SPRITE_MULTICOLOR1,
    SPRITE_MULTICOLOR_SELECT,
    SPRITE_PRIORITY,
    SPRITE_X_EXPANSION,
    SPRITE_Y_EXPANSION,
    TEXT_COLS,
    TEXT_ROWS,
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


def test_tick_under_one_line_worth_of_cycles_does_not_advance(vic):
    vic.tick(CYCLES_PER_LINE - 1)
    assert vic.current_raster == 0


def test_tick_exactly_one_line_worth_of_cycles_advances_by_one(vic):
    vic.tick(CYCLES_PER_LINE)
    assert vic.current_raster == 1


def test_tick_accumulates_partial_cycles_across_calls(vic):
    vic.tick(CYCLES_PER_LINE - 10)
    assert vic.current_raster == 0
    vic.tick(5)
    assert vic.current_raster == 0
    vic.tick(5)
    assert vic.current_raster == 1  # the leftover 10 cycles from both calls crossed the line


def test_tick_can_cross_several_lines_in_one_call(vic):
    vic.tick(CYCLES_PER_LINE * 3 + 1)
    assert vic.current_raster == 3


def test_tick_fires_raster_irq_the_same_as_step_line(vic):
    vic.write_register(RASTER, 2)
    vic.tick(CYCLES_PER_LINE * 2)
    assert vic.current_raster == 2
    assert vic.read_register(IRQ_STATUS) & 0x01


def test_render_frame_fills_border_and_draws_one_character(vic):
    bus = FakeBus()
    vic.write_register(MEMORY_POINTERS, 0x12)  # matrix @ $0400, chars @ $0800
    vic.write_register(BORDER_COLOR, 14)
    vic.write_register(BACKGROUND_COLOR0, 6)
    vic.write_register(CONTROL1, 0x10 | 0x08 | 0x03)  # DEN=1, RSEL=1, YSCROLL=3 (real neutral default)
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


def test_yscroll_at_the_real_default_does_not_clip_the_bottom_row():
    # Regression test: at YSCROLL=3 (the real KERNAL's own default --
    # confirmed empirically in Phase 4, $D011=$1B), all 25 rows must
    # render fully. An earlier bug treated raw y_scroll as the pixel
    # shift instead of (y_scroll - 3), pushing the bottom row's last 3
    # scanlines past the display boundary and silently dropping them --
    # caught from a real screenshot of a full, scrolled screen.
    vic = VicII()
    bus = FakeBus()
    vic.write_register(MEMORY_POINTERS, 0x12)
    vic.write_register(BACKGROUND_COLOR0, 6)
    vic.write_register(CONTROL1, 0x10 | 0x08 | 0x03)  # DEN=1, RSEL=1, YSCROLL=3
    vic.write_register(CONTROL2, 0x08)

    last_row = TEXT_ROWS - 1
    bus.mem[0x0400 + last_row * TEXT_COLS] = 65  # screen code 65 at the bottom row, col 0
    bus.mem[0x0800 + 65 * 8 + 7] = 0xFF  # that char's LAST pixel row: all set
    bus.color_ram[last_row * TEXT_COLS] = 5

    frame = vic.render_frame(bus)

    bottom_pixel_row = BORDER_Y + DISPLAY_HEIGHT - 1
    for x in range(BORDER_X, BORDER_X + 8):
        assert frame[bottom_pixel_row][x] == 5  # must be drawn, not clipped away


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


# -- sprites ----------------------------------------------------------------


def test_sprite_register_helpers_decode_bits_per_sprite(vic):
    vic.write_register(SPRITE_ENABLE, 0b0000_0101)
    assert vic.sprite_enabled(0) is True
    assert vic.sprite_enabled(1) is False
    assert vic.sprite_enabled(2) is True

    vic.write_register(0, 0x50)  # sprite 0 X low byte
    vic.write_register(MSBX, 0b0000_0001)  # sprite 0's X MSB set
    assert vic.sprite_x(0) == 0x150
    assert vic.sprite_y(0) == 0  # not written yet


def test_hires_sprite_renders_at_the_documented_coordinate_offset():
    vic = VicII()
    bus = FakeBus()
    bus.mem[0x3F8] = 5  # sprite 0 pointer -> data at $140
    bus.mem[0x140] = 0xFF  # row 0: first 8 pixels on
    vic.write_register(0, 24 + 3)  # sprite 0 X
    vic.write_register(1, 50 + 2)  # sprite 0 Y
    vic.write_register(SPRITE_ENABLE, 0x01)
    vic.write_register(SPRITE_COLOR_BASE, 2)

    frame = vic.render_frame(bus)

    for col in range(8):
        assert frame[BORDER_Y + 2][BORDER_X + 3 + col] == 2
    assert frame[BORDER_Y + 2][BORDER_X + 2] != 2  # one pixel left of the sprite: untouched


def test_multicolor_sprite_uses_the_shared_and_own_colors():
    vic = VicII()
    bus = FakeBus()
    bus.mem[0x3F8] = 5
    # cell0=01 (multicolor0), cell1=10 (own color), cell2=11 (multicolor1), cell3=00 (transparent)
    bus.mem[0x140] = 0b01_10_11_00
    vic.write_register(0, 24)
    vic.write_register(1, 50)
    vic.write_register(SPRITE_ENABLE, 0x01)
    vic.write_register(SPRITE_MULTICOLOR_SELECT, 0x01)
    vic.write_register(SPRITE_COLOR_BASE, 7)
    vic.write_register(SPRITE_MULTICOLOR0, 3)
    vic.write_register(SPRITE_MULTICOLOR1, 9)

    frame = vic.render_frame(bus)

    assert frame[BORDER_Y][BORDER_X + 0] == 3
    assert frame[BORDER_Y][BORDER_X + 1] == 3
    assert frame[BORDER_Y][BORDER_X + 2] == 7
    assert frame[BORDER_Y][BORDER_X + 3] == 7
    assert frame[BORDER_Y][BORDER_X + 4] == 9
    assert frame[BORDER_Y][BORDER_X + 5] == 9
    assert frame[BORDER_Y][BORDER_X + 6] not in (3, 7, 9)  # transparent -- nothing drawn


def test_sprite_expansion_doubles_pixel_size():
    vic = VicII()
    bus = FakeBus()
    bus.mem[0x3F8] = 5
    bus.mem[0x140] = 0x80  # row 0: only the leftmost pixel on
    vic.write_register(0, 24)
    vic.write_register(1, 50)
    vic.write_register(SPRITE_ENABLE, 0x01)
    vic.write_register(SPRITE_X_EXPANSION, 0x01)
    vic.write_register(SPRITE_Y_EXPANSION, 0x01)
    vic.write_register(SPRITE_COLOR_BASE, 4)

    frame = vic.render_frame(bus)

    for y in range(2):
        for x in range(2):
            assert frame[BORDER_Y + y][BORDER_X + x] == 4
    assert frame[BORDER_Y][BORDER_X + 2] != 4
    assert frame[BORDER_Y + 2][BORDER_X] != 4


def test_sprite_behind_display_is_hidden_by_foreground_pixels():
    vic = VicII()
    bus = FakeBus()
    vic.write_register(MEMORY_POINTERS, 0x12)
    vic.write_register(CONTROL1, 0x10 | 0x08 | 0x03)  # YSCROLL=3 -- real neutral default, no vertical shift
    vic.write_register(CONTROL2, 0x08)
    bus.mem[0x0400] = 65
    bus.mem[0x0800 + 65 * 8] = 0xFF  # character's first row: all foreground
    bus.color_ram[0] = 6

    bus.mem[0x07F8] = 5  # sprite 0 pointer -- matrix base is $0400 here, so pointers live at $07F8
    bus.mem[0x140] = 0xFF  # sprite exactly overlaps that character cell
    vic.write_register(0, 24)
    vic.write_register(1, 50)
    vic.write_register(SPRITE_ENABLE, 0x01)
    vic.write_register(SPRITE_COLOR_BASE, 2)
    vic.write_register(SPRITE_PRIORITY, 0x01)  # sprite 0 drawn behind the display

    frame = vic.render_frame(bus)
    assert frame[BORDER_Y][BORDER_X] == 6  # character's foreground wins


def test_sprite_sprite_collision_persists_until_read_then_can_refire():
    vic = VicII()
    bus = FakeBus()
    bus.mem[0x3F8] = 5  # sprite 0 pointer
    bus.mem[0x3F9] = 5  # sprite 1 pointer -- same shape, same position -> guaranteed overlap
    bus.mem[0x140] = 0xFF
    for n in (0, 1):
        vic.write_register(n * 2, 24)
        vic.write_register(n * 2 + 1, 50)
    vic.write_register(SPRITE_ENABLE, 0b11)
    vic.write_register(SPRITE_COLOR_BASE, 2)
    vic.write_register(SPRITE_COLOR_BASE + 1, 3)

    vic.render_frame(bus)
    assert vic.read_register(COLLISION_SPRITE_SPRITE) == 0b11
    assert vic.read_register(IRQ_STATUS) & 0x04  # IMMC
    assert vic.read_register(COLLISION_SPRITE_SPRITE) == 0  # reading cleared the whole register

    vic.write_register(IRQ_STATUS, 0x04)  # ack IMMC too
    vic.render_frame(bus)  # sprites still overlapping -> a genuinely fresh collision
    assert vic.read_register(COLLISION_SPRITE_SPRITE) == 0b11
    assert vic.read_register(IRQ_STATUS) & 0x04  # fires again since state had been cleared


def test_sprite_background_collision_sets_register_and_fires_irq():
    vic = VicII()
    bus = FakeBus()
    vic.write_register(MEMORY_POINTERS, 0x12)
    vic.write_register(CONTROL1, 0x10 | 0x08 | 0x03)  # YSCROLL=3 -- real neutral default, no vertical shift
    vic.write_register(CONTROL2, 0x08)
    bus.mem[0x0400] = 65
    bus.mem[0x0800 + 65 * 8] = 0xFF
    bus.color_ram[0] = 6

    bus.mem[0x07F8] = 5  # sprite 0 pointer -- matrix base is $0400 here, so pointers live at $07F8
    bus.mem[0x140] = 0xFF
    vic.write_register(0, 24)
    vic.write_register(1, 50)
    vic.write_register(SPRITE_ENABLE, 0x01)
    vic.write_register(SPRITE_COLOR_BASE, 2)

    vic.render_frame(bus)
    assert vic.read_register(COLLISION_SPRITE_BG) == 0x01
    assert vic.read_register(IRQ_STATUS) & 0x02  # IMBC


# -- badlines (condition only -- see docs/vic-ii.md) -------------------------


def test_badlines_disabled_all_frame_if_den_was_off_at_the_latch_line(vic):
    vic.current_raster = DEN_LATCH_LINE - 1
    vic.write_register(CONTROL1, 0x00)  # DEN off
    vic.step_line()  # crosses the latch line with DEN off -> badlines stay off all frame
    vic.write_register(CONTROL1, 0x10)  # turning DEN on now is too late for this frame
    for _ in range(BADLINE_FIRST_LINE, BADLINE_LAST_LINE):
        assert vic.is_badline is False
        vic.step_line()


def test_badlines_fire_on_matching_lines_when_den_was_on_at_the_latch_line(vic):
    vic.current_raster = DEN_LATCH_LINE - 1
    vic.write_register(CONTROL1, 0x10)  # DEN on, YSCROLL=0
    vic.step_line()
    assert vic.current_raster == DEN_LATCH_LINE
    assert vic.is_badline is True  # $30 & 7 == 0 == YSCROLL


def test_badlines_only_match_the_selected_yscroll(vic):
    vic.write_register(CONTROL1, 0x10 | 0x03)  # DEN on, YSCROLL=3
    vic.current_raster = DEN_LATCH_LINE - 1
    vic.step_line()
    assert vic.is_badline is False  # $30 & 7 == 0, YSCROLL == 3 -> no match yet
    for _ in range(3):
        vic.step_line()
    assert vic.current_raster == DEN_LATCH_LINE + 3
    assert vic.is_badline is True
