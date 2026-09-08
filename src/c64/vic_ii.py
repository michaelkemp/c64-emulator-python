"""MOS 6567/6569 VIC-II: registers, standard character-mode and bitmap-mode
rendering, sprites, and collision detection.

See docs/vic-ii.md for the register map, the VIC-II's own bank-switched
view of memory (independent of the CPU's -- see `Bus.read_vic`), the
`$D019` write-1-to-clear interrupt semantics (vs. `$D01E`/`$D01F`'s
read-clears-the-whole-register semantics), the sprite coordinate system,
the bitmap-mode memory layout, and this phase's known gaps (no extended
color mode; badlines are modeled only as a queryable condition, not real
CPU-cycle stealing, since nothing yet interleaves CPU and VIC-II
cycle-by-cycle).
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
BACKGROUND_COLOR1, BACKGROUND_COLOR2 = 0x22, 0x23
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
CYCLES_PER_LINE = 63  # PAL 6569 -- see docs/vic-ii.md's "Clock rate" section
PAL_CLOCK_HZ = 985_248  # the standard-cited PAL C64 PHI2 system clock rate

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
        self._cycles_into_line = 0

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
    def bitmap_mode(self) -> bool:
        return bool(self._registers[CONTROL1] & 0x20)

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
    def bitmap_base(self) -> int:
        """Bitmap mode reuses $D018, but only bit 3 matters (selecting
        between the two 8KB halves of the current 16KB VIC bank) --
        bits 2-1, which pick a character-generator bank in text mode,
        are ignored here. A real, documented hardware quirk, not a
        simplification -- see docs/vic-ii.md."""
        return (self._registers[MEMORY_POINTERS] & 0x08) << 10

    @property
    def border_color(self) -> int:
        return self._registers[BORDER_COLOR] & 0x0F

    @property
    def background_color(self) -> int:
        return self._registers[BACKGROUND_COLOR0] & 0x0F

    @property
    def background_color1(self) -> int:
        return self._registers[BACKGROUND_COLOR1] & 0x0F

    @property
    def background_color2(self) -> int:
        return self._registers[BACKGROUND_COLOR2] & 0x0F

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

    # -- timing --------------------------------------------------------------

    def step_line(self) -> None:
        """Advance by exactly one raster line. `tick()` is the normal,
        cycle-driven way to advance the VIC-II; this lower-level primitive
        is still here directly for tests and anything driving raster
        progression without real CPU cycle counts."""
        self.current_raster = (self.current_raster + 1) % PAL_LINES_PER_FRAME
        if self.current_raster == 0:
            self._badline_enabled_this_frame = False
        if self.current_raster == DEN_LATCH_LINE and self.display_enabled:
            self._badline_enabled_this_frame = True
        if self.current_raster == self.raster_compare:
            self._irq_flags |= IRQ_RASTER

    def tick(self, cycles: int) -> None:
        """Advance by `cycles` PHI2 cycles (see docs/vic-ii.md's "Clock
        rate" section for why 63 cycles/line), crossing however many
        raster lines that spans. Matches `CIA6526.tick(cycles)`'s shape so
        both chips can be driven the same way once something actually
        feeds them real CPU cycle counts -- see "Known gaps" in
        docs/vic-ii.md for why nothing does yet."""
        self._cycles_into_line += cycles
        while self._cycles_into_line >= CYCLES_PER_LINE:
            self._cycles_into_line -= CYCLES_PER_LINE
            self.step_line()

    # -- standard text-mode rendering --------------------------------------

    def render_frame(self, bus) -> list[list[int]]:
        """A 384x272 grid of palette indices (see docs/vic-ii.md for why
        that size): border color everywhere, the 320x200 display area
        drawn in either standard character mode or bitmap mode (extended
        color mode isn't implemented yet), and sprites composited on
        top."""
        frame = [[self.border_color] * FRAME_WIDTH for _ in range(FRAME_HEIGHT)]
        if self.bitmap_mode:
            foreground = self._render_bitmap(bus, frame)
        else:
            foreground = self._render_display(bus, frame)
        self._render_sprites(bus, frame, foreground)
        return frame

    def _visible_area(self) -> tuple[int, int, int, int]:
        """(col_offset, row_offset, visible_cols, visible_rows) -- shared
        by both text and bitmap mode, since RSEL/CSEL (border size) don't
        depend on which mode is active."""
        visible_cols = TEXT_COLS if self.cols_40 else TEXT_COLS - 2
        visible_rows = TEXT_ROWS if self.rows_25 else TEXT_ROWS - 1
        col_offset = (TEXT_COLS - visible_cols) // 2
        row_offset = (TEXT_ROWS - visible_rows) // 2
        return col_offset, row_offset, visible_cols, visible_rows

    def _render_display(self, bus, frame: list[list[int]]) -> set[tuple[int, int]]:
        bg = self.background_color
        col_offset, row_offset, visible_cols, visible_rows = self._visible_area()

        for y in range(DISPLAY_HEIGHT):
            for x in range(DISPLAY_WIDTH):
                frame[BORDER_Y + y][BORDER_X + x] = bg

        foreground: set[tuple[int, int]] = set()
        if not self.display_enabled:
            return foreground

        matrix_base = self.video_matrix_base
        char_base = self.char_base
        x_scroll = self.x_scroll
        # YSCROLL's hardware-neutral value is 3, not 0 (confirmed
        # empirically: the real KERNAL's own default $D011 leaves YSCROLL
        # at 3, and real hardware shows all 25 rows with zero clipping at
        # that default) -- XSCROLL's neutral genuinely is 0, so this
        # isn't a copy-paste asymmetry. Treating raw y_scroll as the
        # offset pushed the bottom row's last 3 scanlines past the
        # display boundary at the real default, clipping it.
        y_shift = self.y_scroll - 3

        mcm = self.multicolor_mode
        bg1, bg2 = self.background_color1, self.background_color2

        for row in range(row_offset, row_offset + visible_rows):
            for col in range(col_offset, col_offset + visible_cols):
                screen_code = bus.read_vic(matrix_base + row * TEXT_COLS + col)
                color_ram = bus.read_color_nibble(row * TEXT_COLS + col)
                char_addr = char_base + screen_code * CHAR_PIXELS
                # Real, per-cell hardware behavior, not a global switch:
                # in multicolor mode, each cell's own color RAM bit 3
                # decides whether *that* cell renders as 4-color
                # multicolor or falls back to ordinary hi-res -- both
                # can appear on the same MCM=1 screen. See docs/vic-ii.md.
                cell_multicolor = mcm and bool(color_ram & 0x08)
                fg = color_ram & 0x07 if cell_multicolor else color_ram

                for line in range(CHAR_PIXELS):
                    byte = bus.read_vic(char_addr + line)
                    py = BORDER_Y + row * CHAR_PIXELS + line + y_shift
                    if not (BORDER_Y <= py < BORDER_Y + DISPLAY_HEIGHT):
                        continue
                    if cell_multicolor:
                        for pair in range(4):
                            code = (byte >> (6 - pair * 2)) & 0b11
                            if code == 0b00:
                                continue
                            color = {0b01: bg1, 0b10: bg2, 0b11: fg}[code]
                            for sub in range(2):  # double-wide pixels
                                px = BORDER_X + col * CHAR_PIXELS + pair * 2 + sub + x_scroll
                                if not (BORDER_X <= px < BORDER_X + DISPLAY_WIDTH):
                                    continue
                                frame[py][px] = color
                                foreground.add((py, px))
                    else:
                        for bit in range(CHAR_PIXELS):
                            px = BORDER_X + col * CHAR_PIXELS + bit + x_scroll
                            if not (BORDER_X <= px < BORDER_X + DISPLAY_WIDTH):
                                continue
                            pixel_on = (byte >> (7 - bit)) & 1
                            frame[py][px] = fg if pixel_on else bg
                            if pixel_on:
                                foreground.add((py, px))
        return foreground

    def _render_bitmap(self, bus, frame: list[list[int]]) -> set[tuple[int, int]]:
        """BMM=1: each text-mode cell's 8 bytes of "character data" come
        from `bitmap_base` instead of a fixed character generator, in the
        same cell order as the video matrix (cell index = row*40+col,
        not a screen-code lookup) -- the video matrix byte itself still
        comes from `video_matrix_base`, but now holds two direct color
        values (high/low nibble) instead of a screen code. MCM=1
        (multicolor bitmap, what real cartridges commonly use) halves
        horizontal resolution to 4 double-wide "pixels" per cell, each
        2 bits picking from: 00=background ($D021), 01=video matrix high
        nibble, 10=video matrix low nibble, 11=color RAM (the same color
        RAM text mode uses). MCM=0 (hi-res bitmap) is 8 real pixels per
        cell, 1 bit each: 1=high nibble, 0=low nibble, no background/color
        RAM involved. See docs/vic-ii.md."""
        bg = self.background_color
        col_offset, row_offset, visible_cols, visible_rows = self._visible_area()

        for y in range(DISPLAY_HEIGHT):
            for x in range(DISPLAY_WIDTH):
                frame[BORDER_Y + y][BORDER_X + x] = bg

        foreground: set[tuple[int, int]] = set()
        if not self.display_enabled:
            return foreground

        matrix_base = self.video_matrix_base
        bitmap_base = self.bitmap_base
        x_scroll = self.x_scroll
        y_shift = self.y_scroll - 3  # see _render_display for why -3
        multicolor = self.multicolor_mode

        for row in range(row_offset, row_offset + visible_rows):
            for col in range(col_offset, col_offset + visible_cols):
                cell = row * TEXT_COLS + col
                color_byte = bus.read_vic(matrix_base + cell)
                color_hi, color_lo = (color_byte >> 4) & 0x0F, color_byte & 0x0F
                color_ram = bus.read_color_nibble(cell)
                cell_addr = bitmap_base + cell * CHAR_PIXELS

                for line in range(CHAR_PIXELS):
                    byte = bus.read_vic(cell_addr + line)
                    py = BORDER_Y + row * CHAR_PIXELS + line + y_shift
                    if not (BORDER_Y <= py < BORDER_Y + DISPLAY_HEIGHT):
                        continue
                    if multicolor:
                        for pair in range(4):
                            code = (byte >> (6 - pair * 2)) & 0b11
                            if code == 0b00:
                                continue
                            color = {0b01: color_hi, 0b10: color_lo, 0b11: color_ram}[code]
                            for sub in range(2):  # double-wide pixels
                                px = BORDER_X + col * CHAR_PIXELS + pair * 2 + sub + x_scroll
                                if not (BORDER_X <= px < BORDER_X + DISPLAY_WIDTH):
                                    continue
                                frame[py][px] = color
                                foreground.add((py, px))
                    else:
                        for bit in range(CHAR_PIXELS):
                            px = BORDER_X + col * CHAR_PIXELS + bit + x_scroll
                            if not (BORDER_X <= px < BORDER_X + DISPLAY_WIDTH):
                                continue
                            pixel_on = (byte >> (7 - bit)) & 1
                            frame[py][px] = color_hi if pixel_on else color_lo
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
                    # Clipped to the interior display area, not the full
                    # frame: the border has *higher* display priority
                    # than sprites on real hardware (verified against
                    # Christian Bauer's article, section 3.8.2's priority
                    # diagram -- "Screen border" sits above "Sprite x" in
                    # both MxDP configurations) -- see docs/vic-ii.md.
                    if not (BORDER_Y <= fy < BORDER_Y + DISPLAY_HEIGHT):
                        continue
                    for ex in range(x_exp):
                        for sub in range(cell_width):
                            fx = BORDER_X + x0 + (cell * cell_width + sub) * x_exp + ex
                            if not (BORDER_X <= fx < BORDER_X + DISPLAY_WIDTH):
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
