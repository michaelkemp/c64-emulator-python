# MOS 6526 CIA (Complex Interface Adapter)

The C64 has two of these: **CIA1** (`$DC00`-`$DCFF`) and **CIA2**
(`$DD00`-`$DDFF`), wired into `Bus`'s I/O window (see `bus.py`'s module
docstring). Both are the same chip -- what differs is what's physically
wired to their two 8-bit ports, and which CPU interrupt line their `IRQ`
output pin drives:

- **CIA1**: Port A (`$DC00`) drives the keyboard matrix's row-select
  lines (and doubles as joystick port 2's input); Port B (`$DC01`) senses
  the matrix's columns (and doubles as joystick port 1). CIA1's interrupt
  output goes to the CPU's **IRQ** line -- this is what the KERNAL uses
  for its 60Hz ("jiffy") clock tick and cursor blink.
- **CIA2**: Port A (`$DD00`) bits 0-1 select which 16KB bank of memory the
  VIC-II reads from (not consumed by anything yet -- VIC-II is Phase 4);
  the rest of Port A plus Port B drive the serial (IEC) bus to disk
  drives/printers and the user port/RS-232 lines -- none of which this
  project emulates. CIA2's interrupt output goes to the CPU's **NMI**
  line, not IRQ.

Primary source: the MOS 6526 preliminary datasheet ([6502.org
PDF](https://6502.org/documents/datasheets/mos/mos_6526_cia_preliminary_nov_1981.pdf)),
cited throughout below. `src/c64/cia.py` implements the chip itself;
`src/c64/keyboard_matrix.py` and `src/c64/joystick.py` implement the two
devices wired to CIA1's ports.

## Register map (16 registers, mirrored every 16 bytes across each CIA's 256-byte window)

| Offset | Name | Purpose |
|---|---|---|
| `$0` | PRA | Data Port A |
| `$1` | PRB | Data Port B |
| `$2` | DDRA | Data Direction Register A (1 = output, 0 = input) |
| `$3` | DDRB | Data Direction Register B |
| `$4`/`$5` | TA LO/HI | Timer A 16-bit latch/counter |
| `$6`/`$7` | TB LO/HI | Timer B 16-bit latch/counter |
| `$8` | TOD 10THS | Time-of-day, tenths of a second (BCD) |
| `$9` | TOD SEC | Time-of-day, seconds (BCD) |
| `$A` | TOD MIN | Time-of-day, minutes (BCD) |
| `$B` | TOD HR | Time-of-day, hours (BCD) + bit 7 = PM |
| `$C` | SDR | Serial Data Register |
| `$D` | ICR | Interrupt Control Register |
| `$E` | CRA | Control Register A (Timer A) |
| `$F` | CRB | Control Register B (Timer B) |

## Ports (PRA/PRB, DDRA/DDRB)

A DDR bit of 1 makes the corresponding port bit an output (reads back
whatever was last written); 0 makes it an input. On real hardware an
input bit floats and is weakly pulled high unless something external
pulls it low -- the same "undriven bits read as 1" model already used for
the 6510's port (`cpu_port.py`), extended here with an actual external
device: `CIA6526` takes an optional `port_coupler` (see
`keyboard_matrix.py`'s `Cia1Ports`) that, given which bits *this* port is
currently driving low, reports which bits get pulled low on the *other*
port. That's what makes both scan directions work -- normal keyboard
scanning (drive rows on PRA, sense columns on PRB) and the reversed
scan a few programs use.

## Timers A and B

Each is a 16-bit down counter with its own 16-bit latch (reload value).
Per the datasheet:

- Writing the low byte only ever updates the *latch's* low byte.
- Writing the high byte updates the latch's high byte, **and** if the
  timer isn't currently running, also loads the counter from the latch
  immediately -- so writing both bytes while stopped sets the counter
  directly.
- On underflow (counter reaches 0 and would tick again): the counter
  reloads from the latch, the corresponding ICR flag bit sets, and in
  one-shot mode the timer's own START bit clears automatically (it stops
  itself; continuous mode just keeps counting).
- The control register's FORCE LOAD bit (bit 4) is a write-only strobe --
  it immediately reloads the counter from the latch regardless of
  running state, and always reads back as 0.

Control register bits (CRA `$E`, CRB `$F` -- identical except where noted):

| Bit | CRA | CRB |
|---|---|---|
| 0 | START | START |
| 1 | PBON (route Timer A output onto PB6) | PBON (PB7) |
| 2 | OUTMODE (0=pulse, 1=toggle) | OUTMODE |
| 3 | RUNMODE (0=continuous, 1=one-shot) | RUNMODE |
| 4 | FORCE LOAD (strobe) | FORCE LOAD (strobe) |
| 5 | INMODE (0=count Φ2, 1=count CNT pin) | INMODE bit 0 |
| 6 | SPMODE (0=serial in, 1=serial out) | INMODE bit 1 |
| 7 | TODIN (0=60Hz, 1=50Hz) | ALARM (0=TOD regs are the clock, 1=they're the alarm) |

Timer B's 2-bit INMODE adds two modes Timer A doesn't have: count Timer
A's underflows, or count Timer A's underflows gated by CNT -- the
well-known trick real software uses to chain A+B into an effective
32-bit timer.

**Known gap**: the CNT pin isn't modeled at all (nothing in this project
drives it), so INMODE settings that depend on it (`count CNT`, and the
CNT-gated Timer B mode) never tick. Only Φ2 counting and the "count Timer
A underflow" mode work. PB6/PB7 timer output is modeled only as an
in-memory toggle/pulse flag read back through `PRB` when `PBON` is set --
there's no consumer for it yet (no audio path wired to it), so its exact
pulse-width timing hasn't been validated against real hardware.

## Time-of-day clock (TOD)

BCD registers, 12-hour format with bit 7 of the hours register as AM/PM.
Two documented quirks this implementation models because real software
(including the KERNAL) depends on them:

- **Reading the hours register latches all four TOD registers** so a
  reader can't see the clock tick mid-read (e.g. seconds rolling from 59
  to 00 between reading minutes and seconds); the latch releases the next
  time the tenths register is read.
- **Writing the hours register stops the clock; writing the tenths
  register (last, by convention) restarts it** -- lets software set all
  four registers atomically without the clock advancing mid-write.

CRB's ALARM bit (bit 7) redirects writes to `$8`-`$B` into a separate
alarm register instead of the clock; when the (unlatched) clock equals
the alarm, ICR's TOD-alarm flag sets once.

**Fixed** (was "known gap: nothing drives real elapsed time into this
clock"). `CIA6526.tick(cycles)` -- the same real-elapsed-PHI2-cycles call
`Machine.step()` already makes every step for the timers -- now also
advances TOD: it accumulates `cycles * 10` (units of a tenth of a PHI2
cycle) and calls `tick_tenth_second()` once the accumulator reaches
`PAL_CLOCK_HZ`. Tracked as an all-integer tenths-of-a-cycle count rather
than a fractional cycles-per-tenth float deliberately -- `PAL_CLOCK_HZ`
(985248) isn't evenly divisible by 10, so a naive float accumulator
subtracting 98524.8 repeatedly drifts short by a hair at exact-second
boundaries (caught by a test asserting an exact boundary, not just
approximately-right timing). CRA bit 7 (`TodClock.rate_50hz`, the real
50Hz-vs-60Hz mains-divisor select) is still stored/read back correctly
for software that checks it, but doesn't change tick timing here -- there's
no real external TOD pin/mains signal in this project to apply it to, so
ticking directly off the known-exact system clock rate is more accurate
to real wall-time than modeling a synthetic mains-derived divider chain
would be. Verified against the real KERNAL via `Machine`: both CIA1 and
CIA2's independent TOD clocks advance correctly over real elapsed cycles.
Real-world impact was real but rare (software reading TOD for actual
wall-time, not most games/demos). Not to be confused with the *jiffy
clock* (`$A0`-`$A2`, a KERNAL software counter incremented by its own IRQ
handler on CIA1 Timer A underflow) -- a different mechanism from this TOD
register file entirely, and the thing that was already verified
incrementing back in Phase 7 (see `CLAUDE.md`).

## Interrupt Control Register (ICR, `$D`)

Five event sources, each a bit: 0=Timer A underflow, 1=Timer B underflow,
2=TOD alarm, 3=SDR full, 4=FLAG pin edge. Bit 7 is the IRQ output itself.

- **Reading** ICR returns whichever event bits are currently pending,
  plus bit 7 set if any *enabled* pending bit caused the actual interrupt
  -- and reading **clears all pending flags and deasserts the interrupt**
  (a classic, easy-to-get-wrong CIA behavior: the read is destructive).
- **Writing** ICR sets or clears bits in the *mask* (which events are
  enabled), never the pending flags directly: bit 7 of the written value
  selects the operation -- 1 means "set every bit that's 1 in this write
  into the mask", 0 means "clear every bit that's 1 in this write from
  the mask".

**Known gap, still open**: bit 4 (FLAG pin) never sets -- the FLAG pin
isn't modeled (nothing drives it: no cassette, no user-port device).

**Fixed since this was written**: `CIA6526.irq_line` reflects the chip's
own IRQ output correctly, *and* `Machine.step()` (`docs/machine.md`,
Phase 7) now wires it to the CPU's actual IRQ pin (`cia1.irq_line or vic.
irq_line` delivers `cpu.irq()`) and CIA2's to NMI (edge-triggered). A
distinct fix from the TOD one above (that's about driving TOD's own
*internal* clock forward; this is about the chip's IRQ *output* reaching
the CPU at all) -- both are now resolved, just at different times.

## Serial Data Register (SDR, `$C`)

On real hardware this is a genuine shift register: in output mode
(`SPMODE`=1) it shifts a byte out one bit per CNT pulse and sets the
ICR's SDR-full flag after all 8 bits go out; in input mode it does the
reverse. This project has no serial bus device (no disk drive emulation
exists, and this repo isn't planning one) and no CNT source, so **this is
the biggest simplification in this file**: writing SDR in output mode
completes "instantly" (sets the ICR flag on the same call, no real bit
timing), and reads just return whatever was last written -- nothing
drives real serial input. Fine for now since nothing depends on real
IEC/RS-232 timing; revisit if that ever changes.

## Keyboard matrix and joysticks

`KeyboardMatrix` (`keyboard_matrix.py`) models the C64's 8x8 key matrix
electrically -- `press(row, col)`/`release(row, col)`, and bidirectional
sensing (`sense_columns`/`sense_rows`) so scanning works in either
direction, matching real hardware's symmetric wiring. `Joystick`
(`joystick.py`) models a single digital joystick's up/down/left/right/fire
switches, active low, on whichever port it's plugged into. `Cia1Ports`
composes both into the single `port_coupler` `CIA6526` expects.

Real input reaches `Joystick` via `peripherals/joystick_input.py`
(`JoystickInput`) -- the numeric keypad drives *one* port at a time
(defaulting to port 2, the real-world convention for single-joystick
software), switchable at runtime with F2, since this project has no
real second physical input device to dedicate to each port.

**Resolved (Phase 9), empirically, not from either disputed source**: two
well-regarded community references disagreed with each other on the exact
row/column assignment ([c64-wiki.com/wiki/Keyboard](https://www.c64-wiki.com/wiki/Keyboard)
vs. [sta.c64.org/cbm64kbdlay.html](http://sta.c64.org/cbm64kbdlay.html)).
Rather than trust either, this project's own staged, real KERNAL settled
it directly: for each of the 64 `(row, col)` positions, `KeyboardMatrix.press`
that position alone, run `Machine` far enough for the real IRQ-driven
keyboard scan to see it, and call the KERNAL's own official `GETIN`
routine (`$FFE4`) to read back the actual PETSCII character the real ROM
decodes it to. The result is internally consistent (digits/letters land
in the expected QWERTY-shaped rows; exactly 4 positions never produce a
character -- the two shifts, Commodore, and CTRL, exactly the 4 real
modifier keys) and matches `sta.c64.org`'s table almost exactly, catching
one real error in it along the way (`(0, 2)` is `CRSR RIGHT`, PETSCII
`$1D`, not `←` as that table claims). `KeyboardMatrix.KEY_POSITIONS` (a
`dict[str, tuple[int, int]]`) and `press_key`/`release_key` are built on
this verified table -- see `keyboard_matrix.py`.

`RESTORE` isn't part of the matrix at all on real hardware -- it wires
directly to the CPU's NMI line (diode-OR'd with CIA2's own NMI output),
not through CIA1 like every other key. Not modeled as a `KeyboardMatrix`
position; a future peripherals bridge should call `machine.cpu.nmi()`
directly for it, the same edge-triggered way `Machine.step()` already
handles CIA2.
