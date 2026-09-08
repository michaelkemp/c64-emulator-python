# MOS 6567/6569 VIC-II

Phase 4 added **standard character (text) mode**. Phase 5 added
**sprites** (fetch, rendering, X/Y expansion, multicolor, priority,
collision detection), the **badline condition**, and a cycle-driven
`tick(cycles)` clock interface (added just after Phase 5, prompted by
planning ahead for Phase 6's SID) -- but still not real cycle-accurate
timing: no bitmap/extended-color modes, and no actual CPU-cycle stealing
(see "Known gaps" below for exactly why, and what would need to exist
first). No further phase is currently planned to close that specific
gap; see `docs/roadmap.md`.

![The real KERNAL+BASIC ROMs, booted unmodified through this project's
CPU+Bus+CIA+VIC-II stack and rendered by `scripts/render_frame.py`
-- the genuine C64 boot screen.](c64-boot-screen.png)

Primary sources: Christian Bauer's cycle-by-cycle reverse-engineering
article ([cebix.net/VIC-Article.txt](https://www.cebix.net/VIC-Article.txt))
and the official preliminary MOS 6567 datasheet
([6502.org PDF](https://6502.org/documents/datasheets/mos/mos_6567_vic_ii_preliminary.pdf)),
cited throughout below.

## Clock rate: standardizing on PAL

Real C64s come in several timing variants, verified rather than assumed
(confirmed via web search against multiple sources, cross-checked with
VICE's own local ROM database on the machine this was developed on --
`/usr/share/vice/C64/default.vrs`):

| Chip | Video standard | Cycles/line | Lines/frame |
|---|---|---|---|
| 6569 | PAL | 63 | 312 |
| 6567R56A ("old" NTSC) | NTSC | 64 | 262 |
| 6567R8 ("new" NTSC) | NTSC | 65 | 263 |

This project standardizes on **PAL** (`CYCLES_PER_LINE = 63`,
`PAL_LINES_PER_FRAME = 312`, `PAL_CLOCK_HZ = 985_248`), for three
reasons: it's the single well-defined variant (NTSC's R56A/R8 split
alone causes real compatibility differences between actual C64 units);
Christian Bauer's article above -- this project's primary VIC-II
reference -- is written around the PAL 6569; and the KERNAL this project
already validates against (`901227-03`, staged via `scripts/stage_roms.sh`)
is VICE's own default pairing for its PAL "C64" model. That ROM isn't
locked to PAL, though -- this and other late-revision KERNALs
auto-detect PAL/NTSC in software at runtime -- so the choice of region is
entirely this emulator's own VIC-II timing constants, not something the
ROM forces.

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
| `$00`-`$0F` | M0X/M0Y..M7X/M7Y | Sprite X/Y coordinates |
| `$10` | MSBX | Sprite X coordinate 9th bit, one per sprite |
| `$11` | Control register 1 | bit7=RST8, bit6=ECM, bit5=BMM, bit4=DEN, bit3=RSEL, bits2-0=YSCROLL |
| `$12` | RASTER | Current raster line (read, low 8 bits) / raster IRQ compare (write, low 8 bits) |
| `$13`/`$14` | LPX/LPY | Light pen (not modeled) |
| `$15` | ME | Sprite enable, one bit per sprite |
| `$16` | Control register 2 | bit4=MCM, bit3=CSEL, bits2-0=XSCROLL |
| `$17` | YE | Sprite Y expansion, one bit per sprite |
| `$18` | Memory pointers | bits7-4=video matrix base, bits3-1=char base |
| `$19` | Interrupt register | bit0=raster, bit1=sprite-bg collision, bit2=sprite-sprite collision, bit3=light pen, bit7=IRQ |
| `$1A` | Interrupt enable | same bit positions as `$19`, bits 0-3 only |
| `$1B` | DM | Sprite-to-display priority, one bit per sprite (1 = sprite drawn behind non-background display pixels) |
| `$1C` | MC | Sprite multicolor mode select, one bit per sprite |
| `$1D` | XE | Sprite X expansion, one bit per sprite |
| `$1E`/`$1F` | MM/MC | Sprite-sprite / sprite-background collision (read clears the whole register; writes ignored) |
| `$20` | Border color |
| `$21`-`$24` | Background colors 0-3 (only color 0 matters in standard text mode) |
| `$25`/`$26` | Sprite multicolor 0/1 (shared across every multicolor sprite) |
| `$27`-`$2E` | Sprite colors 0-7 (each sprite's own color) |

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
only display mode implemented so far -- multicolor text, extended color,
and bitmap modes (`MCM`/`ECM`/`BMM`) are left unimplemented (reading/
writing those bits is harmless; `VicII` just doesn't act differently on
them yet). Sprites (a separate mechanism layered on top, not one of these
modes) are implemented -- see below.

`DEN` (`$11` bit 4): when clear, the real chip stops fetching video
matrix data entirely and the screen shows nothing but background/border.
Modeled here as simply skipping the text render and filling the interior
with background color 0 -- not the real "opens the border" cycle-exact
trick some demos use (that needs real cycle-accurate timing -- see
"Known gaps" below). Sprites are unaffected by `DEN` (real hardware
behavior: sprite DMA doesn't depend on it).

`RSEL`/`CSEL` (24 vs 25 rows, 38 vs 40 columns) and `XSCROLL`/`YSCROLL`
are honored by shifting/clipping which part of the fixed 320×200
character grid gets drawn -- not by actually changing the real hardware's
border geometry pixel-for-pixel, which is a raster-timing concern (see
"Known gaps").

**`YSCROLL`'s neutral value is 3, not 0** (`XSCROLL`'s genuinely is 0 --
this isn't a copy-paste asymmetry). The real KERNAL's own default leaves
`$D011`'s `YSCROLL` bits at 3 (confirmed empirically in Phase 4:
`$D011=$1B`), and real hardware shows all 25 rows with zero clipping at
that default. An earlier version of this code added raw `y_scroll` as
the pixel shift, which at the real default pushed the bottom row's last
3 scanlines past the display boundary and silently dropped them --
invisible in the Phase 4/5 boot-screen checks (which never had content
reach the last row) and only caught later from a real screenshot of a
full, scrolled screen. Fixed by using `y_scroll - 3` as the shift, so the
real default produces zero net offset; genuine non-default values now
shift content up/down from that neutral point (with the same top/bottom
clipping approximation this section already documents, just centered
correctly).

## Sprites

Each of the 8 sprites is 24×21 pixels in standard (hires) mode, or
12×21 double-width-pixel in multicolor mode, optionally doubled again in
either or both dimensions (`XE`/`YE`). A sprite's shape data is 63 bytes
(21 rows × 3 bytes = 24 bits/row), located by its **sprite pointer**: the
video matrix's *last* 8 bytes (`matrix_base + $3F8` through `+ $3FF`,
one per sprite) each hold a byte that, ×64, gives the shape data's
address -- fetched through `Bus.read_vic` exactly like character data, so
the same bank/char-ROM-substitution rules in the section above apply
equally to sprite data (a sprite pointer that happens to land on
`$1000`-`$1FFF` in banks 0/2 will, correctly, fetch character ROM bytes
as "sprite data").

**Coordinates**: `$D000`-`$D00F` give each sprite's X/Y as CPU-register
values, not frame pixels -- the universally-cited offset from a sprite's
own X/Y to the top-left corner of the visible text/graphics area is
**X=24, Y=50** (i.e. frame pixel = register value minus that offset, then
placed relative to the border margin the same way text pixels are).
`$D010` (MSBX) supplies each sprite's 9th X bit for positions past 255.

**Multicolor** (`$D01C`, one bit per sprite): each 2-bit code in a
sprite's data means `00`=transparent, `01`=`$D025` (shared multicolor 0),
`10`=that sprite's own color (`$D027`+n), `11`=`$D026` (shared multicolor
1). In standard mode each single bit means transparent (0) or the
sprite's own color (1).

**Priority** (`$D01B`, one bit per sprite): a clear bit draws the sprite
in front of everything from the main display; a set bit draws it behind
only the main display's *foreground* pixels (background color 0 always
loses to a sprite, regardless of this bit) -- it has no effect on
sprite-vs-sprite ordering, which is always by sprite number (0 highest,
7 lowest, matching real hardware).

**The border always wins over sprites.** Verified against Christian
Bauer's article (section 3.8.2's priority diagram): "Screen border" sits
at the *highest*-priority position, above every sprite, in both `MxDP`
configurations -- sprites are clipped to the interior 320x200 display
area, never drawn into the border, matching real hardware's default
behavior. This is exactly why "sprites in the border" is a well-known,
sought-after *demo trick* rather than something that happens for free:
defeating this masking on real hardware needs precise raster-timing
manipulation (the same DEN-latched-at-line-`$30` mechanism `is_badline`
already models the condition for, combined with cycle-exact timing this
project doesn't implement -- see "Known gaps"), not just positioning a
sprite past the edge. An earlier version of this code clipped sprites to
the full frame (border included) instead of the interior area, letting
them render on top of the border in the default case where real hardware
wouldn't -- caught from a real screenshot, not written correctly the
first time.

## Collision detection (`$D01E`/`$D01F`)

Different clearing rule from `$D019` above, easy to mix up: reading
`$D01E` (sprite-sprite) or `$D01F` (sprite-background) returns the
accumulated collision bits and **clears the entire register** -- not
write-1-to-clear, and not per-bit. `VicII` accumulates newly-detected
collisions into these registers across `render_frame` calls and only
raises the corresponding `$D019` flag (`IMMC`/`IMBC`) for bits that
weren't already set -- so a collision that's still ongoing next frame
doesn't keep re-firing the interrupt until the CPU actually reads (and
thereby clears) the register, matching real hardware.

## Badlines (condition only, not real cycle-stealing)

A "badline" is the well-known VIC-II behavior (Bauer's article, the
section this project leans on most for Phase 5+) where, on specific
raster lines, the chip steals cycles from the CPU to fetch a line's worth
of video matrix/color data ahead of drawing it. A line is bad when all of:
the raster line is in `$30`-`$F7`, its low 3 bits equal `YSCROLL`
(`$D011` bits 2-0), **and** `DEN` was set at the moment the raster
reached line `$30` for this frame specifically (not just "is DEN set
now") -- that specific latch is the mechanism behind the classic
"FLD"/border-opening demo trick (hold `DEN` clear through line `$30` and
badlines never happen for the rest of that frame, freeing up cycles the
real chip would otherwise have stolen).

`VicII.is_badline` implements the *condition* exactly as above and is
unit-tested against it, including the DEN-latch quirk. What it does
**not** do is actually remove cycles from anything -- see the next
section for why.

## Known gaps in this phase

- **No bitmap mode, no extended-color mode.** `BMM`/`ECM` are stored but
  inert -- no phase currently covers them; add one if real software needs
  them.
- **Real CPU-cycle stealing still doesn't happen.** `VicII.tick(cycles)`
  (matching `CIA6526.tick(cycles)`'s shape) advances the raster line
  counter and fires raster IRQs precisely against however many PHI2
  cycles it's fed -- driven with the exact cycle counts
  `c6502.emulator.cpu.CPU.step()` already returns per instruction (via
  its `StepResult.cycles`), raster IRQ timing becomes accurate to within
  one CPU instruction, the standard approximation most non-cycle-stepped
  6502 emulators use. `is_badline` tells you *whether* a line would
  steal cycles, and sprite DMA isn't cycle-costed at all -- but nothing
  actually *spends* that cost against the CPU's own budget, because
  nothing yet interleaves the CPU and VIC-II together in a real running
  loop that could remove cycles from one to give to the other. That
  needs a real top-level "machine" object, which doesn't exist yet (the
  same gap already flagged in `docs/cia.md` for `irq_line` and real
  elapsed time, and for wiring CIA1/VIC-II's IRQ output and CIA2's NMI
  output to the CPU's actual interrupt pins).
- **Frame/border geometry is an approximation**, not real hardware's
  raster geometry: `render_frame` produces a fixed 384×272 image (320×200
  visible text/graphics area plus a 32px/36px border margin -- the same
  convention VICE's own default PAL screenshot uses), not the exact pixel
  counts of a real VIC-II's visible raster area. Sprites are positioned
  using the real X=24/Y=50 coordinate convention against that
  approximate frame, so a sprite near the border edge won't necessarily
  line up with where it would sit against a real raster display.
- **The 16-color palette is an aesthetic approximation**, not a
  calibrated reproduction of any specific real hardware's composite video
  output (unlike the keyboard matrix ambiguity in `docs/cia.md`, this
  isn't a factual question with one right answer -- real units vary, and
  no verification was attempted here).
