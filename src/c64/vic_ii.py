"""MOS 6567/6569 VIC-II: registers, and standard character-mode rendering.

See docs/vic-ii.md for the register map, the VIC-II's own bank-switched
view of memory (independent of the CPU's -- see `Bus.read_vic`), the
`$D019` write-1-to-clear interrupt semantics, and this phase's known gaps
(no sprites, no bitmap/extended-color modes, not cycle-accurate).
"""

from __future__ import annotations

CONTROL1, RASTER = 0x11, 0x12
CONTROL2 = 0x16
MEMORY_POINTERS = 0x18
IRQ_STATUS, IRQ_ENABLE = 0x19, 0x1A
BORDER_COLOR = 0x20
BACKGROUND_COLOR0 = 0x21
COLLISION_SPRITE_SPRITE, COLLISION_SPRITE_BG = 0x1E, 0x1F

NUM_REGISTERS = 0x2F  # $2F-$3F are unconnected, handled separately

IRQ_RASTER = 0x01
IRQ_SPRITE_BG = 0x02
IRQ_SPRITE_SPRITE = 0x04
IRQ_LIGHT_PEN = 0x08
IRQ_FLAG = 0x80
IRQ_ENABLE_MASK = 0x0F

TEXT_COLS, TEXT_ROWS = 40, 25
CHAR_PIXELS = 8
DISPLAY_WIDTH, DISPLAY_HEIGHT = TEXT_COLS * CHAR_PIXELS, TEXT_ROWS * CHAR_PIXELS
BORDER_X, BORDER_Y = 32, 36
FRAME_WIDTH = DISPLAY_WIDTH + 2 * BORDER_X
FRAME_HEIGHT = DISPLAY_HEIGHT + 2 * BORDER_Y

PAL_LINES_PER_FRAME = 312

# An aesthetic approximation, not a calibrated real-hardware palette --
# see docs/vic-ii.md.
PALETTE = [
    (0x00, 0x00, 0x00), (0xFF, 0xFF, 0xFF), (0x88, 0x00, 0x00), (0xAA, 0xFF, 0xEE),
    (0xCC, 0x44, 0xCC), (0x00, 0xCC, 0x55), (0x00, 0x00, 0xAA), (0xEE, 0xEE, 0x77),
    (0xDD, 0x88, 0x55), (0x66, 0x44, 0x00), (0xFF, 0x77, 0x77), (0x33, 0x33, 0x33),
    (0x77, 0x77, 0x77), (0xAA, 0xFF, 0x66), (0x00, 0x88, 0xFF), (0xBB, 0xBB, 0xBB),
]


class VicII:
    def __init__(self) -> None:
        self._registers = bytearray(NUM_REGISTERS)
        self.current_raster = 0
        self._raster_compare_high = 0
        self._irq_flags = 0x00
        self._irq_enable = 0x00

    # -- register file --------------------------------------------------

    def read_register(self, offset: int) -> int:
        if offset >= NUM_REGISTERS:
            return 0xFF
        if offset == CONTROL1:
            base = self._registers[CONTROL1] & 0x7F
            return base | (0x80 if self.current_raster & 0x100 else 0x00)
        if offset == RASTER:
            return self.current_raster & 0xFF
        if offset == IRQ_STATUS:
            asserted = bool(self._irq_flags & self._irq_enable)
            return self._irq_flags | 0x70 | (IRQ_FLAG if asserted else 0x00)
        if offset == IRQ_ENABLE:
            return self._irq_enable | 0xF0
        if offset in (COLLISION_SPRITE_SPRITE, COLLISION_SPRITE_BG):
            return 0x00  # no sprites yet -- see docs/vic-ii.md
        return self._registers[offset]

    def write_register(self, offset: int, value: int) -> None:
        value &= 0xFF
        if offset >= NUM_REGISTERS:
            return
        if offset == CONTROL1:
            self._registers[CONTROL1] = value & 0x7F
            self._raster_compare_high = 0x100 if value & 0x80 else 0x00
            return
        if offset == RASTER:
            self._registers[RASTER] = value
            return
        if offset == IRQ_STATUS:
            self._irq_flags &= ~(value & 0x0F) & 0xFF
            return
        if offset == IRQ_ENABLE:
            self._irq_enable = value & IRQ_ENABLE_MASK
            return
        if offset in (COLLISION_SPRITE_SPRITE, COLLISION_SPRITE_BG):
            return  # read-only
        self._registers[offset] = value

    # -- control register fields -----------------------------------------

    @property
    def raster_compare(self) -> int:
        return self._raster_compare_high | self._registers[RASTER]

    @property
    def display_enabled(self) -> bool:
        return bool(self._registers[CONTROL1] & 0x10)

    @property
    def rows_25(self) -> bool:
        return bool(self._registers[CONTROL1] & 0x08)

    @property
    def y_scroll(self) -> int:
        return self._registers[CONTROL1] & 0x07

    @property
    def multicolor_mode(self) -> bool:
        return bool(self._registers[CONTROL2] & 0x10)

    @property
    def cols_40(self) -> bool:
        return bool(self._registers[CONTROL2] & 0x08)

    @property
    def x_scroll(self) -> int:
        return self._registers[CONTROL2] & 0x07

    @property
    def video_matrix_base(self) -> int:
        return (self._registers[MEMORY_POINTERS] & 0xF0) << 6

    @property
    def char_base(self) -> int:
        return (self._registers[MEMORY_POINTERS] & 0x0E) << 10

    @property
    def border_color(self) -> int:
        return self._registers[BORDER_COLOR] & 0x0F

    @property
    def background_color(self) -> int:
        return self._registers[BACKGROUND_COLOR0] & 0x0F

    # -- interrupts -------------------------------------------------------

    @property
    def irq_line(self) -> bool:
        return bool(self._irq_flags & self._irq_enable)

    # -- timing (not cycle-accurate -- see docs/vic-ii.md) -----------------

    def step_line(self) -> None:
        self.current_raster = (self.current_raster + 1) % PAL_LINES_PER_FRAME
        if self.current_raster == self.raster_compare:
            self._irq_flags |= IRQ_RASTER

    # -- standard text-mode rendering --------------------------------------

    def render_frame(self, bus) -> list[list[int]]:
        """A 384x272 grid of palette indices (see docs/vic-ii.md for why
        that size): border color everywhere, with the 320x200 text area
        drawn in standard character mode (multicolor/bitmap/extended-color
        modes aren't implemented yet)."""
        frame = [[self.border_color] * FRAME_WIDTH for _ in range(FRAME_HEIGHT)]
        self._render_display(bus, frame)
        return frame

    def _render_display(self, bus, frame: list[list[int]]) -> None:
        bg = self.background_color
        visible_cols = TEXT_COLS if self.cols_40 else TEXT_COLS - 2
        visible_rows = TEXT_ROWS if self.rows_25 else TEXT_ROWS - 1
        col_offset = (TEXT_COLS - visible_cols) // 2
        row_offset = (TEXT_ROWS - visible_rows) // 2

        for y in range(DISPLAY_HEIGHT):
            for x in range(DISPLAY_WIDTH):
                frame[BORDER_Y + y][BORDER_X + x] = bg

        if not self.display_enabled:
            return

        matrix_base = self.video_matrix_base
        char_base = self.char_base
        x_scroll, y_scroll = self.x_scroll, self.y_scroll

        for row in range(row_offset, row_offset + visible_rows):
            for col in range(col_offset, col_offset + visible_cols):
                screen_code = bus.read_vic(matrix_base + row * TEXT_COLS + col)
                fg = bus.read_color_nibble(row * TEXT_COLS + col)
                char_addr = char_base + screen_code * CHAR_PIXELS
                for line in range(CHAR_PIXELS):
                    byte = bus.read_vic(char_addr + line)
                    py = BORDER_Y + row * CHAR_PIXELS + line + y_scroll
                    if not (BORDER_Y <= py < BORDER_Y + DISPLAY_HEIGHT):
                        continue
                    for bit in range(CHAR_PIXELS):
                        px = BORDER_X + col * CHAR_PIXELS + bit + x_scroll
                        if not (BORDER_X <= px < BORDER_X + DISPLAY_WIDTH):
                            continue
                        pixel_on = (byte >> (7 - bit)) & 1
                        frame[py][px] = fg if pixel_on else bg
