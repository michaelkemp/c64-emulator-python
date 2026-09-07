# MOS 6567/6569 VIC-II

Phase 4 scope only: **standard character (text) mode**, no sprites, no
bitmap or extended-color modes, and deliberately not cycle-accurate (no
badlines, no exact raster timing) -- see `docs/roadmap.md`'s Phase 4/5
split. This file will grow in Phase 5 to cover sprites and the real
cycle-by-cycle timing.

![The real KERNAL+BASIC ROMs, booted unmodified through this project's
CPU+Bus+CIA+VIC-II stack and rendered by `scripts/render_frame.py`
-- the genuine C64 boot screen.](c64-boot-screen.png)

Primary sources: Christian Bauer's cycle-by-cycle reverse-engineering
article ([cebix.net/VIC-Article.txt](https://www.cebix.net/VIC-Article.txt))
and the official preliminary MOS 6567 datasheet
([6502.org PDF](https://6502.org/documents/datasheets/mos/mos_6567_vic_ii_preliminary.pdf)),
cited throughout below.

## The VIC-II has its own view of memory -- not the CPU's

This is the single most important thing to get right before rendering
anything, and it's easy to miss: the VIC-II does **not** read memory
through the CPU's LORAM/HIRAM/CHAREN bank-switched view (`bus.py`'s
`read8`). It has its own, independent 16KB window into the 64KB address
space, selected by **CIA2 port A bits 0-1** (see `docs/cia.md`) -- and
inverted from the intuitive order:

| PA1 PA0 | VIC-II sees |
|---|---|
| 1 1 | Bank 0: `$0000`-`$3FFF` (default at reset) |
| 1 0 | Bank 1: `$4000`-`$7FFF` |
| 0 1 | Bank 2: `$8000`-`$BFFF` |
| 0 0 | Bank 3: `$C000`-`$FFFF` |

Within that 16KB window, two more registers pick where the video matrix
(screen memory) and character data live:

- **`$D018` bits 7-4 (VM13-VM10)**: video matrix base = value × `$400`
  (1KB steps; the matrix is 1000 bytes, `40×25`).
- **`$D018` bits 3-1 (CB13-CB11)**: character data base = value × `$800`
  (2KB steps -- 8 possible locations spanning the 16KB bank).

**Character ROM is hardwired into the VIC-II's view**, regardless of bank
switching, in one specific place: whenever the character-base register
would select offset `$1000`-`$1FFF` *within* bank 0 or bank 2 (i.e.
absolute `$1000`-`$1FFF` or `$9000`-`$9FFF`), the VIC-II sees the real
character ROM there instead of RAM -- even though the CPU, looking at the
very same absolute addresses through its own bank-switched view, might
see RAM, BASIC ROM, or I/O. This is why the C64's default setup (bank 0,
char base `$1000`) shows the ROM font without any RAM copy: `Bus.read_vic`
implements exactly this, kept deliberately separate from `Bus.read8`.
Banks 1 and 3 never expose character ROM to the VIC-II at all, and even
banks 0/2 only do so at that one specific offset -- picking any of the
other seven char-base steps gets you RAM, always.

Color RAM (`$D800`-`$DBFF`) is the one exception to all of this: it's
real, always-present 4-bit SRAM that the VIC-II reads directly,
independent of both the CPU's bank switching *and* the VIC-II's own
16KB-window selection (`Bus.read_color_nibble`).

## Register map (used registers only; `$2F`-`$3F` are unconnected -- always read `$FF`, writes ignored)

| Offset | Name | Purpose |
|---|---|---|
| `$00`-`$0F` | M0X/M0Y..M7X/M7Y | Sprite X/Y coordinates (Phase 5) |
| `$10` | MSBX | Sprite X coordinate MSBs (Phase 5) |
| `$11` | Control register 1 | bit7=RST8, bit6=ECM, bit5=BMM, bit4=DEN, bit3=RSEL, bits2-0=YSCROLL |
| `$12` | RASTER | Current raster line (read, low 8 bits) / raster IRQ compare (write, low 8 bits) |
| `$13`/`$14` | LPX/LPY | Light pen (not modeled) |
| `$15` | Sprite enable (Phase 5) |
| `$16` | Control register 2 | bit4=MCM, bit3=CSEL, bits2-0=XSCROLL |
| `$17` | Sprite Y expansion (Phase 5) |
| `$18` | Memory pointers | bits7-4=video matrix base, bits3-1=char base |
| `$19` | Interrupt register | bit0=raster, bit1=sprite-bg collision, bit2=sprite-sprite collision, bit3=light pen, bit7=IRQ |
| `$1A` | Interrupt enable | same bit positions as `$19`, bits 0-3 only |
| `$1B`-`$1D` | Sprite priority/multicolor/X-expansion (Phase 5) |
| `$1E`/`$1F` | Sprite collision registers (Phase 5; always read 0 until sprites exist) |
| `$20` | Border color |
| `$21`-`$24` | Background colors 0-3 (only color 0 matters in standard text mode) |
| `$25`/`$26` | Sprite multicolor 0/1 (Phase 5) |
| `$27`-`$2E` | Sprite colors 0-7 (Phase 5) |

`$11`'s RST8 bit is a well-known trap: **on read** it's the 9th bit of
the *current* raster line; **on write** it's the 9th bit of the *raster
compare* value (the line a raster IRQ should fire on). Same bit position,
two different underlying values -- `VicII` models them as separate
9-bit fields (`current_raster`, `raster_compare`) for exactly this
reason.

## Interrupts: write-1-to-clear, *not* read-to-clear

Unlike the CIAs (`docs/cia.md`: reading the ICR clears every pending
flag), the VIC-II's `$19` is **not** cleared by reading it. Clearing a
flag requires **writing a 1 to that specific bit** of `$19` -- writing a
0 to a bit leaves it alone. Bits 4-6 of both `$19` and `$1A` are
unconnected and always read as 1.

## Standard text mode rendering (BMM=0, ECM=0, MCM=0)

For each of the 25 rows × 40 columns: read a screen code from the video
matrix, use it as an index into the 8-byte-per-character character data
(`char_base + screen_code * 8`, one byte per pixel row), and for each of
the 8 bits in each of those 8 bytes: set bit = the column's color-RAM
nibble (foreground), clear bit = background color 0 (`$21`). This is the
only mode Phase 4 implements -- multicolor text, extended color, and
bitmap modes (`MCM`/`ECM`/`BMM`) are left unimplemented (reading/writing
those bits is harmless; `VicII` just doesn't act differently on them
yet), same as sprites.

`DEN` (`$11` bit 4): when clear, the real chip stops fetching video
matrix data entirely and the screen shows nothing but background/border.
Modeled here as simply skipping the text render and filling the interior
with background color 0 -- not the real "opens the border" cycle-exact
trick some demos use (that needs real raster timing, Phase 5).

`RSEL`/`CSEL` (24 vs 25 rows, 38 vs 40 columns) and `XSCROLL`/`YSCROLL`
are honored by shifting/clipping which part of the fixed 320×200
character grid gets drawn -- not by actually changing the real hardware's
border geometry pixel-for-pixel, which is a raster-timing concern
deferred to Phase 5.

## Known gaps in this phase

- **No sprites, no bitmap mode, no extended-color mode.** Their registers
  exist and are read/write-storable but do nothing yet (Phase 5, except
  bitmap/ECM which have no phase yet -- add one if real software needs
  them before sprites do).
- **Not cycle-accurate**: no badlines, no exact per-cycle raster/border
  timing, no sprite-stealing of CPU cycles. `VicII.step_line()` just
  advances the raster counter by one line at a time on demand; nothing
  yet drives it from real CPU cycle counts (same "nothing assembles a
  real running machine yet" gap noted in `docs/cia.md`).
- **Frame/border geometry is an approximation**, not real hardware's
  raster geometry: `render_frame` produces a fixed 384×272 image (320×200
  visible text/graphics area plus a 32px/36px border margin -- the same
  convention VICE's own default PAL screenshot uses), not the exact pixel
  counts of a real VIC-II's visible raster area.
- **The 16-color palette is an aesthetic approximation**, not a
  calibrated reproduction of any specific real hardware's composite video
  output (unlike the keyboard matrix ambiguity in `docs/cia.md`, this
  isn't a factual question with one right answer -- real units vary, and
  no verification was attempted here).
