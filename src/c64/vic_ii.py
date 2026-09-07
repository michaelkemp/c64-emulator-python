"""MOS 6567/6569 VIC-II: registers, standard character-mode rendering,
sprites, and collision detection.

See docs/vic-ii.md for the register map, the VIC-II's own bank-switched
view of memory (independent of the CPU's -- see `Bus.read_vic`), the
`$D019` write-1-to-clear interrupt semantics (vs. `$D01E`/`$D01F`'s
read-clears-the-whole-register semantics), the sprite coordinate system,
and this phase's known gaps (no bitmap/extended-color modes; badlines are
modeled only as a queryable condition, not real CPU-cycle stealing, since
nothing yet interleaves CPU and VIC-II cycle-by-cycle).
"""

from __future__ import annotations

CONTROL1, RASTER = 0x11, 0x12
CONTROL2 = 0x16
SPRITE_ENABLE = 0x15
SPRITE_Y_EXPANSION = 0x17
MEMORY_POINTERS = 0x18
IRQ_STATUS, IRQ_ENABLE = 0x19, 0x1A
SPRITE_PRIORITY = 0x1B
SPRITE_MULTICOLOR_SELECT = 0x1C
SPRITE_X_EXPANSION = 0x1D
COLLISION_SPRITE_SPRITE, COLLISION_SPRITE_BG = 0x1E, 0x1F
BORDER_COLOR = 0x20
BACKGROUND_COLOR0 = 0x21
SPRITE_MULTICOLOR0, SPRITE_MULTICOLOR1 = 0x25, 0x26
SPRITE_COLOR_BASE = 0x27  # + sprite number (0-7)
MSBX = 0x10  # X coordinate 9th bit, one per sprite

NUM_REGISTERS = 0x2F  # $2F-$3F are unconnected, handled separately

NUM_SPRITES = 8
SPRITE_HEIGHT = 21
SPRITE_HIRES_WIDTH_CELLS = 24
SPRITE_MULTICOLOR_WIDTH_CELLS = 12
# The universally-cited offset between a sprite's own X/Y registers and
# the top-left corner of the visible text/graphics area -- see
# docs/vic-ii.md.
SPRITE_X_ORIGIN_OFFSET = 24
SPRITE_Y_ORIGIN_OFFSET = 50

BADLINE_FIRST_LINE, BADLINE_LAST_LINE = 0x30, 0xF7
DEN_LATCH_LINE = 0x30

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
        self._collision_sprite_sprite = 0x00
        self._collision_sprite_bg = 0x00
        self._badline_enabled_this_frame = False

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
        if offset == COLLISION_SPRITE_SPRITE:
            value = self._collision_sprite_sprite
            self._collision_sprite_sprite = 0x00  # reading clears the whole register
            return value
        if offset == COLLISION_SPRITE_BG:
            value = self._collision_sprite_bg
            self._collision_sprite_bg = 0x00
            return value
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

    # -- sprite register fields -------------------------------------------

    def sprite_enabled(self, n: int) -> bool:
        return bool(self._registers[SPRITE_ENABLE] & (1 << n))

    def sprite_x(self, n: int) -> int:
        msb = 0x100 if self._registers[MSBX] & (1 << n) else 0
        return msb | self._registers[n * 2]

    def sprite_y(self, n: int) -> int:
        return self._registers[n * 2 + 1]

    def sprite_x_expanded(self, n: int) -> bool:
        return bool(self._registers[SPRITE_X_EXPANSION] & (1 << n))

    def sprite_y_expanded(self, n: int) -> bool:
        return bool(self._registers[SPRITE_Y_EXPANSION] & (1 << n))

    def sprite_multicolor(self, n: int) -> bool:
        return bool(self._registers[SPRITE_MULTICOLOR_SELECT] & (1 << n))

    def sprite_behind_display(self, n: int) -> bool:
        return bool(self._registers[SPRITE_PRIORITY] & (1 << n))

    def sprite_color(self, n: int) -> int:
        return self._registers[SPRITE_COLOR_BASE + n] & 0x0F

    @property
    def sprite_multicolor0(self) -> int:
        return self._registers[SPRITE_MULTICOLOR0] & 0x0F

    @property
    def sprite_multicolor1(self) -> int:
        return self._registers[SPRITE_MULTICOLOR1] & 0x0F

    # -- interrupts -------------------------------------------------------

    @property
    def irq_line(self) -> bool:
        return bool(self._irq_flags & self._irq_enable)

    # -- badlines (condition only -- see docs/vic-ii.md) --------------------

    @property
    def is_badline(self) -> bool:
        return (
            self._badline_enabled_this_frame
            and BADLINE_FIRST_LINE <= self.current_raster <= BADLINE_LAST_LINE
            and (self.current_raster & 0x07) == self.y_scroll
        )

    # -- timing (not cycle-accurate -- see docs/vic-ii.md) -----------------

    def step_line(self) -> None:
        self.current_raster = (self.current_raster + 1) % PAL_LINES_PER_FRAME
        if self.current_raster == 0:
            self._badline_enabled_this_frame = False
        if self.current_raster == DEN_LATCH_LINE and self.display_enabled:
            self._badline_enabled_this_frame = True
        if self.current_raster == self.raster_compare:
            self._irq_flags |= IRQ_RASTER

    # -- standard text-mode rendering --------------------------------------

    def render_frame(self, bus) -> list[list[int]]:
        """A 384x272 grid of palette indices (see docs/vic-ii.md for why
        that size): border color everywhere, the 320x200 text area drawn
        in standard character mode (multicolor/bitmap/extended-color
        modes aren't implemented yet), and sprites composited on top."""
        frame = [[self.border_color] * FRAME_WIDTH for _ in range(FRAME_HEIGHT)]
        foreground = self._render_display(bus, frame)
        self._render_sprites(bus, frame, foreground)
        return frame

    def _render_display(self, bus, frame: list[list[int]]) -> set[tuple[int, int]]:
        bg = self.background_color
        visible_cols = TEXT_COLS if self.cols_40 else TEXT_COLS - 2
        visible_rows = TEXT_ROWS if self.rows_25 else TEXT_ROWS - 1
        col_offset = (TEXT_COLS - visible_cols) // 2
        row_offset = (TEXT_ROWS - visible_rows) // 2

        for y in range(DISPLAY_HEIGHT):
            for x in range(DISPLAY_WIDTH):
                frame[BORDER_Y + y][BORDER_X + x] = bg

        foreground: set[tuple[int, int]] = set()
        if not self.display_enabled:
            return foreground

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
                        if pixel_on:
                            foreground.add((py, px))
        return foreground

    # -- sprites ------------------------------------------------------------

    def _render_sprites(self, bus, frame: list[list[int]], foreground: set[tuple[int, int]]) -> None:
        matrix_base = self.video_matrix_base
        sprite_pixels: dict[int, dict[tuple[int, int], int]] = {
            n: self._sprite_pixels(bus, matrix_base, n) for n in range(NUM_SPRITES) if self.sprite_enabled(n)
        }

        new_sprite_sprite = 0
        new_sprite_bg = 0
        enabled = list(sprite_pixels)
        for i_idx, i in enumerate(enabled):
            if sprite_pixels[i].keys() & foreground:
                new_sprite_bg |= 1 << i
            for j in enabled[i_idx + 1 :]:
                if sprite_pixels[i].keys() & sprite_pixels[j].keys():
                    new_sprite_sprite |= (1 << i) | (1 << j)
        self._register_collisions(new_sprite_sprite, new_sprite_bg)

        for n in range(NUM_SPRITES - 1, -1, -1):  # sprite 0 drawn last -> highest priority
            pixels = sprite_pixels.get(n)
            if not pixels:
                continue
            behind = self.sprite_behind_display(n)
            for pos, color in pixels.items():
                if behind and pos in foreground:
                    continue
                frame[pos[0]][pos[1]] = color

    def _sprite_pixels(self, bus, matrix_base: int, n: int) -> dict[tuple[int, int], int]:
        pointer = bus.read_vic(matrix_base + 0x3F8 + n)
        data_addr = (pointer * 64) & 0x3FFF
        x0 = self.sprite_x(n) - SPRITE_X_ORIGIN_OFFSET
        y0 = self.sprite_y(n) - SPRITE_Y_ORIGIN_OFFSET
        x_exp = 2 if self.sprite_x_expanded(n) else 1
        y_exp = 2 if self.sprite_y_expanded(n) else 1
        multicolor = self.sprite_multicolor(n)
        own_color = self.sprite_color(n)
        color_for_code = {0b01: self.sprite_multicolor0, 0b10: own_color, 0b11: self.sprite_multicolor1}
        cell_width = 2 if multicolor else 1
        cells_per_row = SPRITE_MULTICOLOR_WIDTH_CELLS if multicolor else SPRITE_HIRES_WIDTH_CELLS

        pixels: dict[tuple[int, int], int] = {}
        for row in range(SPRITE_HEIGHT):
            bits = (
                (bus.read_vic(data_addr + row * 3) << 16)
                | (bus.read_vic(data_addr + row * 3 + 1) << 8)
                | bus.read_vic(data_addr + row * 3 + 2)
            )
            for cell in range(cells_per_row):
                if multicolor:
                    code = (bits >> (22 - cell * 2)) & 0b11
                    if code == 0:
                        continue
                    color = color_for_code[code]
                else:
                    if not (bits >> (23 - cell)) & 1:
                        continue
                    color = own_color
                for ey in range(y_exp):
                    fy = BORDER_Y + y0 + row * y_exp + ey
                    if not (0 <= fy < FRAME_HEIGHT):
                        continue
                    for ex in range(x_exp):
                        for sub in range(cell_width):
                            fx = BORDER_X + x0 + (cell * cell_width + sub) * x_exp + ex
                            if not (0 <= fx < FRAME_WIDTH):
                                continue
                            pixels[(fy, fx)] = color
        return pixels

    def _register_collisions(self, sprite_sprite_bits: int, sprite_bg_bits: int) -> None:
        new_ss = sprite_sprite_bits & ~self._collision_sprite_sprite & 0xFF
        new_bg = sprite_bg_bits & ~self._collision_sprite_bg & 0xFF
        self._collision_sprite_sprite |= sprite_sprite_bits
        self._collision_sprite_bg |= sprite_bg_bits
        if new_ss:
            self._irq_flags |= IRQ_SPRITE_SPRITE
        if new_bg:
            self._irq_flags |= IRQ_SPRITE_BG
