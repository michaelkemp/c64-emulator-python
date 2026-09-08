# Cartridges (.crt)

`src/c64/cartridge.py` loads real `.crt` cartridge images and
`src/c64/bus.py` maps them into memory exactly the way the real
6510/PLA address decode does. **Only "generic" hardware type 0 is
supported**: plain, static ROM at $8000-$9FFF (ROML) and/or
$A000-$BFFF (ROMH), with no bank-switching registers at all. Real
`.crt` files can name over 100 other hardware types (Action Replay,
Ocean type, Fun Play, System 3, various freezer carts...), each with
its own bespoke, reverse-engineered bank-switching behavior at
$DE00-$DFFF -- real, additional scope, not attempted here. See
`docs/roadmap.md`'s Phase 11 for the status of that.

Primary reference: the standard `.crt` format documentation
([ist.uwaterloo.ca/~schepers/formats/CRT.TXT](https://ist.uwaterloo.ca/~schepers/formats/CRT.TXT)),
cross-checked directly against a real, working 16K cartridge image
(a Galaxian conversion) parsed by hand before writing `cartridge.py` --
not assumed from the spec alone. The LORAM/HIRAM/GAME/EXROM memory-map
interaction below was verified against VICE's own `c64meminit.c` source
directly (a first web search of a summarized wiki table gave an
internally self-contradictory answer for the exact question that
mattered here -- real, working emulator source settled it, not a
secondary summary).

## File format

Main header (64 bytes):

| Offset | Size | Field |
|---|---|---|
| `$00` | 16 | `"C64 CARTRIDGE  "` signature (space-padded) |
| `$10` | 4 | Header length, big-endian (minimum `$40`) |
| `$14` | 2 | Version, big-endian |
| `$16` | 2 | Hardware type ID, big-endian -- must be `0` (generic) here |
| `$18` | 1 | EXROM line, raw value (`0`=asserted/low, `1`=inactive/high) |
| `$19` | 1 | GAME line, raw value (same convention) |
| `$1A` | 6 | Reserved |
| `$20` | 32 | Cartridge name, null-padded |

One or more CHIP packets follow the header, one per ROM image:

| Offset (from packet start) | Size | Field |
|---|---|---|
| `+$00` | 4 | `"CHIP"` signature |
| `+$04` | 4 | Packet length (header + data), big-endian |
| `+$08` | 2 | Chip type, big-endian -- must be `0` (ROM) here |
| `+$0A` | 2 | Bank number, big-endian -- must be `0` here (no bank switching) |
| `+$0C` | 2 | Load address, big-endian -- must be `$8000` or `$A000` here |
| `+$0E` | 2 | Image size, big-endian |
| `+$10` | *size* | Raw ROM data |

A single CHIP packet loaded at `$8000` with size `$4000` (16KB) covers
*both* ROML and ROMH -- the first 8KB is ROML, the second is ROMH (this
is exactly how the real, verified Galaxian cartridge is structured, not
a hypothetical case). A CHIP packet can also target ROML and ROMH as
two separate 8KB packets instead; both layouts are supported.

`exrom`/`game` on the raw byte values (not inverted to an "active"
boolean, deliberately -- matches how every reference table, including
VICE's own source, documents this, to avoid a silent double-negation
bug):

| GAME | EXROM | Mode |
|---|---|---|
| 1 | 1 | No cartridge |
| 1 | 0 | 8K cartridge (ROML only) |
| 0 | 0 | 16K cartridge (ROML + ROMH) |
| 0 | 1 | Ultimax (**not supported** -- see Known gaps) |

## Memory-map interaction (verified against VICE's `c64meminit.c`)

Cartridge ROM joins the *same* PLA-driven bank-switching `bus.py`'s own
module docstring already documents for BASIC/KERNAL ROM (LORAM/HIRAM/
CHAREN from `CpuPort`) -- it isn't an independent override:

| GAME | EXROM | LORAM | HIRAM | $8000-$9FFF | $A000-$BFFF |
|---|---|---|---|---|---|
| 1 | 0 | 1 | 1 | ROML | BASIC ROM (8K cart: ROMH doesn't exist) |
| 0 | 0 | 1 | 1 | ROML | ROMH |
| 0 | 0 | 0 | 1 | RAM | ROMH |
| 0 | 0 | * | 0 | RAM | RAM |
| 1 or 0 | 0 | 0 | * | RAM | (per the no-cartridge table in `bus.py`, ROML always needs LORAM) |

Which reduces to a real, verified asymmetry -- not a guess, and not
what an "EXROM/GAME simply override everything" assumption would
predict: **ROML needs EXROM active *and* LORAM *and* HIRAM** (confirmed
directly from VICE's `c64meminit_roml_config` array); **ROMH (16K mode
only) needs only HIRAM**, independent of LORAM (confirmed from
`c64meminit_romh_config`). In practice LORAM/HIRAM are `1`/`1` for the
entire time BASIC/KERNAL run normally (the KERNAL sets `$01` to `$37`
at boot and essentially never changes it), so this mostly matters for
software that deliberately re-banks `$01` -- but it's implemented to
the real, verified table, not the common case alone.

Writes to $8000-$9FFF/$A000-$BFFF while cartridge ROM is mapped land in
the real C64 RAM underneath, exactly like BASIC/KERNAL ROM already
works in `bus.py` -- not ignored. A generic cartridge has no registers
of its own at $DE00-$DFFF to intercept those writes differently.

## Autostart: zero extra code needed

The real KERNAL's own boot routine checks for the "CBM80" signature
(bytes `$C3 $C2 $CD $38 $30` -- high-bit-set "CBM" + ASCII "80") at
`$8004`-`$8008`, right after the cartridge's own cold-reset/NMI vectors
at `$8000`-`$8003`, and jumps to the cartridge's cold-reset vector if
found. Since this project boots the real, unmodified KERNAL ROM, this
autostart detection works automatically the moment ROML is mapped
correctly -- verified directly: booting with a real, autostart-signed
16K cartridge loaded, the genuine KERNAL jumped into the cartridge's
own entry point within 33 CPU steps of reset, with no cartridge-aware
code in this project's boot path at all.

## Usage

Drop a `.crt` file in `cartridge-slot/` (gitignored, like `roms/`) and
`scripts/run_c64.py` auto-loads the first file found there; pass
`--cartridge path/to/file.crt` to load a specific one instead.
Programmatically: `Machine.from_roms(roms_dir, cartridge_path=...)` or
build a `Cartridge` and pass it to `Machine`/`Bus` directly.

`Cartridge.from_file` raises `UnsupportedCartridge` (never a silent
guess or truncation) for: any hardware type other than 0, Ultimax mode,
non-ROM chip types (RAM/Flash), bank-switched CHIP packets, or CHIP
packets at an unexpected load address/size.

## Known gaps

- **Ultimax mode isn't modeled.** GAME=0/EXROM=1 maps ROMH into
  $E000-$FFFF instead of $A000-$BFFF and disables most RAM elsewhere --
  a real, different code path from the plain 8K/16K cases here.
  `Cartridge.from_file` refuses to load one rather than mapping it
  wrong.
- **No bank-switching hardware types.** Every real cartridge hardware
  type other than 0 needs its own emulated bank-select register
  behavior at $DE00-$DFFF. Not attempted -- each one is its own
  bespoke, reverse-engineered spec.
- **No cartridge RAM or Flash chip types**, only ROM (`chip_type=0`).
- **Only single-bank cartridges** (`bank=0` in every CHIP packet).
