# Disk (1541) support

## Real hardware, briefly

A 1541 is not "a file on a bus" -- it's a **complete second computer**:
its own 6502 CPU, its own 2KB RAM, its own 16KB DOS ROM, and two 6522 VIA
chips (a different chip from the C64's own CIA, not built here) driving
the stepper motor, read/write head, and the serial bus interface. The C64
talks to it by bit-banging a serial protocol (IEC, derived from IEEE-488)
over CIA2's port A lines (ATN/CLK/DATA) -- the KERNAL's `LISTEN`/`TALK`/
`ACPTR`/`CIOUT` routines toggle those lines with real cycle-level timing,
and the drive's *own* 6502 program watches its own VIA and replies. Both
machines run concurrently. Real floppies also store data GCR-encoded (not
plain bytes) -- though `.d64` files are a convenience format that has
already been decoded to plain sector bytes, sidestepping that specific
layer regardless of which strategy below is used.

## Two real implementation strategies

**1. KERNAL-trap "fake" loading** (what most emulators default to,
including VICE when "true drive emulation" is off): intercept the
KERNAL's own LOAD/SAVE calls at fixed, revision-stable addresses, parse/
write the `.d64`'s track-sector-directory structure directly in Python,
and hand back bytes as if a real load happened -- no drive CPU, no VIA,
no serial bus at all. Fast to build, no second ROM needed, and
`LOAD"$",8` / `LOAD"program",8,1` work immediately for anything using the
stock KERNAL loader.

**2. True drive emulation**: a full second machine, cross-stepped with
the first over an emulated IEC bus, exactly like real hardware. The
CPU core is directly reusable (already Dormann-validated, chip-agnostic),
and the 1541's own memory map is much simpler than the C64's (no bank-
switching) -- what's genuinely new is a VIA chip module (similar scope to
`cia.py`), the drive's own tiny bus, the serial-bus protocol itself (the
fiddly, timing-sensitive part), and a real 1541 DOS ROM (see "ROM
licensing" below).

**The real, unavoidable tradeoff**: strategy 1 cannot run software with a
custom "fastloader" -- a large fraction of commercial disk games replace
the KERNAL's slow stock loader with their own hand-optimized routine that
talks to real drive hardware/timing directly, bypassing the KERNAL
entirely. A trap at the KERNAL level never sees those calls at all; the
game just hangs waiting for a drive that isn't really there. Only
strategy 2 handles that correctly, because it's genuinely how the
hardware works.

**This project builds strategy 1 first** (Phase 11, disk) -- a
deliberate, disclosed simplification, not an oversight, matching the same
"document the real gap" convention as every other chip doc here. Strategy
2 is a separate, much larger undertaking (comparable in scope to real
per-scanline VIC-II rendering), reserved for later and gated on actually
sourcing/verifying a 1541 ROM first.

## ROM licensing (for strategy 2, when it's tackled)

Not fetched or vendored here -- same discipline as `docs/roadmap.md`'s
Phase 1 C64 ROM research, and the same lesson applies: **VICE bundling
something is not proof it's legitimately licensed for redistribution**
(this is the exact "unverified blanket permission" pattern Phase 1 already
caught once for the KERNAL/BASIC/chargen ROMs -- don't repeat the mistake
here).

For the record, so a future session knows where to look without
re-deriving this: VICE's own source tree ships real 1541 DOS ROM images
by their real historical Commodore part numbers at
`vice/data/DRIVES/dos1541-325302-01+901229-05.bin` (16,384 bytes --
verified directly against VICE's real GitHub source, not assumed from a
filename) -- DOS 2.6, the standard 1541 ROM (part numbers 325302-01 +
901229-05). Several other drive ROMs live alongside it (1541-II, 1551,
1570/1571, 1581, and the older 2031/2040/3040/4040 IEEE drives). None of
this should be fetched automatically by this project; if/when strategy 2
is built, extend `scripts/stage_roms.sh`'s same pattern -- stage the
user's own already-legitimately-acquired copy into gitignored `roms/`,
never download one.

## `.d64` format (verified against the standard reference, ist.uwaterloo.ca/~schepers/formats/D64.TXT)

Standard 35-track image, 683 total sectors, 174,848 bytes:

| Track range | Sectors/track | Sectors |
|---|---|---|
| 1-17 | 21 | 357 |
| 18-24 | 19 | 133 |
| 25-30 | 18 | 108 |
| 31-35 | 17 | 85 |

**BAM (Block Availability Map), track 18 sector 0**:

| Offset | Content |
|---|---|
| `$00-01` | First directory sector T/S (always `18/1`) |
| `$02` | DOS version (`$41` = standard 2A) |
| `$04-8F` | Per-track BAM: 4 bytes/track -- byte 0 = free-sector count, bytes 1-3 = 24-bit free bitmap (bit=1 means free) |
| `$90-9F` | Disk name, 16 chars, `$A0`-padded |
| `$A2-A3` | Disk ID (2 bytes) |
| `$A5-A6` | DOS type (`"2A"`) |

**Directory entries, track 18 sectors 1+ (8 entries per 256-byte sector)**:

| Offset | Content |
|---|---|
| `$00-01` | Next directory sector T/S (only meaningful on each sector's *first* entry; `$00/$00` once there's no next sector) |
| `$02` | File type: bits 0-3 = type (0=DEL, 1=SEQ, 2=PRG, 3=USR, 4=REL), bit 6 = locked, bit 7 = closed (unset = a "*" splat/incomplete file) |
| `$03-04` | First T/S of the file's data chain |
| `$05-14` | Filename, 16 chars, `$A0`-padded |
| `$1E-1F` | File size in sectors (little-endian) -- a block count, not exact bytes |

**File data chain**: each sector's first 2 bytes are `(next_track,
next_sector)`; `next_track == 0` marks the last sector, and `next_sector`
then holds the offset of the *last valid byte* in that sector (so that
sector's real data is bytes `$02` through `next_sector`, inclusive --
`next_sector - 1` bytes, not 254). Real hardware interleaves sectors
(10 for file data, 3 for directory sectors) to give the physical disk
time to settle between reads; this project's allocator doesn't reproduce
that, since it only matters for real spinning-disk seek/settle time, not
correctness in an emulated context -- a disclosed simplification, not a
bug.

## KERNAL trap protocol (strategy 1)

Traps fire at the **fixed KERNAL jump-table addresses** `$FFD5` (LOAD)
and `$FFD8` (SAVE) -- these addresses are stable across every real KERNAL
revision specifically so machine-language programs can rely on them
without needing source-level compatibility (real hardware's own `$FFD5`
is itself just `JMP ($0330)` through a RAM vector, `$FFD8` similarly
through `$0332` -- trapping at the fixed address catches the call before
that indirection, the same point VICE's own "kernal traps" intercept at).
Only calls with device number 8+ (set via `SETLFS`) are trapped; device 0
(keyboard) and 1 (cassette) fall through to the real, unmodified KERNAL
routine untouched.

Everything *before* the trap point (BASIC tokenizing `LOAD`/`SAVE`,
calling `SETNAM`/`SETLFS`) and *after* it (BASIC's own post-LOAD
relinking of `VARTAB`/program-end pointers, which runs on the returned
end address exactly as it would after a real load) is genuine,
unmodified KERNAL/BASIC ROM code -- the trap only replaces the "transfer
bytes over a serial bus to/from a real spinning disk" part, verified
against real KERNAL calling conventions rather than assumed:

**LOAD ($FFD5) on entry**: `$B7` = filename length, `$BB`/`$BC` =
filename pointer (low/high), `$BA` = device number, `$B9` = secondary
address. A PRG file's own first two bytes are *always* its own claimed
load address, and are *always* discarded from the actual loaded data --
this doesn't depend on secondary address at all (verified before
implementing, not assumed: an earlier draft of this trap got exactly
this wrong, treating secondary-address-0 as "the header bytes are real
data", which would have corrupted every loaded program by 2 bytes).
Secondary address only picks *which* address is used as the
destination: 0 = the address in X/Y, ignoring the file's own header
value -- what BASIC's plain `LOAD"NAME",8` does, forcing `$0801`; 1 =
the file's own header value instead, ignoring X/Y -- what
`LOAD"NAME",8,1` does, needed for machine-language programs with their
own absolute load address. **On return**: Carry clear + X/Y = end
address + 1 on success; Carry set + an error code in A on failure.

**SAVE ($FFD8) on entry**: A = a zero-page address holding a 16-bit
pointer to the *start* of the data to save (BASIC points this at `$2B`/
`$2C`, `TXTTAB`, the start of program text); X/Y = the *end* address
(exclusive) of the data to save (BASIC supplies its own current
end-of-program pointer here). **On return**: Carry clear on success,
set + an error code in A on failure -- **but "file already exists" and
"disk full" are genuinely not failures at this level**: the real KERNAL
error table (verified against sta.c64.org/cbm64krnerr.html, not
assumed) only defines codes 1-9, none of them "file exists" or "disk
full". Those are disk-error-channel-only conditions on real hardware
(e.g. "63, FILE EXISTS,00,00", visible only via `OPEN 15,8,15` +
`INPUT#15`, not modeled here) -- so a plain `SAVE"NAME",8` to an
existing filename returns Carry clear (success) from the KERNAL's own
point of view while correctly, silently not overwriting the file. An
earlier version of this trap fabricated Carry-set codes for both cases
that don't actually exist, producing garbled on-screen text instead of
a clean error when actually run against the real BASIC ROM -- caught by
testing it, not left as an assumption.

## Known gaps

- **No fastloader support** -- the fundamental, disclosed limitation of
  strategy 1 (see above). A game that hangs after `LOAD` rather than
  erroring cleanly is the expected symptom; not a bug to chase blindly.
- **No copy protection** -- anything relying on intentionally malformed
  sectors, half-tracks, or weak bits (real protection schemes some
  commercial games use) can't be represented by the plain `.d64` sector
  model at all, regardless of strategy.
- **No sector interleave** -- see the `.d64` format section above; a
  disclosed simplification, not a bug, since it only matters for real
  disk rotation timing.
- **Single physical drive-select convention, not yet a hardware
  limitation check** -- real 1541s are jumper-configurable to device
  8-11; this project's trap dispatches by device number to whichever
  image is mounted for that number, with no artificial single-drive
  restriction.
