# Gap analysis: this project vs. VICE

Requested directly: "a full look at the vice source and see if there is
gaps in what we have done compared to vice -- so that we understand the
gaps in our implementation and then we can decide if we battle them or
not." This is a documentation pass only -- nothing in this file changed
any code. It compares this project's actual behavior against VICE's real
source (`github.com/sysfce2/VICE`, fetched directly, not summarized from
memory) across every chip this project emulates, so gaps can be picked
off deliberately later rather than discovered one crashed cartridge at a
time.

**Headline finding**: this project's existing per-chip docs
(`docs/cia.md`, `docs/vic-ii.md`, `docs/sid.md`, `docs/6502-reference.md`,
`docs/cartridge.md`) already named almost everything VICE's real source
reveals -- a direct result of the "document known gaps as you find them"
convention this project has followed since Phase 3. Genuinely new items
below are marked **NEW**; everything else is "already documented,"
sometimes with added precision from reading VICE/reSID's actual source
rather than a summary.

## CPU / 6510 core

| | |
|---|---|
| VICE | `6510core.c` fully implements undocumented opcodes (LAX, SAX, DCP, ISC/ISB, SLO, RLA, SRE, RRA, ANC, ALR, ARR, SBX, multi-byte NOPs) -- real software (copy protection, cracktros, some commercial games) uses them, occasionally as an anti-emulation check. |
| This project | `src/c6502/emulator/opcodes.py` only maps documented opcodes; any other byte raises `IllegalOpcodeError`, an uncaught Python exception that kills the process. |
| Status | Already documented as a deliberate choice (`docs/6502-reference.md`: "we are not implementing... loud failure so bugs are visible"). **NEW precision**: the "loud failure" is a full process crash, not a caught/logged error -- worth knowing before running an arbitrary real cartridge unattended. Also confirmed: Klaus Dormann's *standard* suite (already used here) doesn't exercise illegal opcodes at all -- a separate "extended" suite does, not fetched by this project, so this area isn't just unimplemented, it's untested even in principle. |
| Real-world impact | None for KERNAL/BASIC (already proven). Real risk for arbitrary cartridges/demos -- the same category of software that already surfaced two real VIC-II gaps this session. |
| Battle it? | Cheap partial win available: change the crash to a caught, logged skip (treat as multi-byte NOP) so an unknown cartridge degrades instead of dying. Full illegal-opcode *correctness* is a bigger lift (needs the extended Dormann suite) and only matters if a specific desired program needs it. |

## CIA 6526 (both chips)

| | |
|---|---|
| VICE | `ciacore.c` (2617 lines): timer A→B cascade, TOD alarm matching, PB6/PB7 toggle-output pins, a real cycle-driven SDR/serial shift register. |
| This project | `src/c64/cia.py` already implements timer cascade, TOD alarm, and PB6/PB7 toggle. The one real simplification: `_write_sdr()` completes the shift instantly instead of over 8 real CNT pulses. |
| Status | Already documented in full -- `docs/cia.md` explicitly names the CNT pin, TOD-not-driven-by-real-elapsed-time, FLAG pin/bit 4, and the SDR-instant-completion simplification ("the biggest simplification in this file"). No new findings. |
| Real-world impact | Low -- already verified against real KERNAL CIA init. SDR-instant-completion would only matter for real serial-bus (disk drive) traffic, which doesn't exist yet regardless. |
| Battle it? | Not yet -- revisit if/when disk drive emulation (rest of Phase 11) needs real serial-bus timing. |

## Memory map / PLA / bank-switching

| | |
|---|---|
| VICE | `c64mem.c` models the `$01` port's "fading bits" (undriven bits 3-7 float to their last-driven value and decay back to 1 after a measured delay) -- a real hardware quirk a handful of demos/protection schemes exploit. |
| This project | `cpu_port.py` reads any undriven bit as an unconditional 1, no decay/float timing. The PLA/ROML/ROMH bank-switching truth table itself was already cross-checked against VICE's real `c64meminit.c` config arrays this session (for cartridge support) and matches. |
| Status | Already documented verbatim in `cpu_port.py`'s own module docstring, including the "a handful of demos exploit this" framing. No new findings. |
| Real-world impact | Negligible for everything tested so far; only a narrow class of demos deliberately probes this. |
| Battle it? | No -- correctly deprioritized already. |

## Cartridge hardware-type breadth

| | |
|---|---|
| VICE | `vice/src/c64/cart/` contains **111 separate hardware-type source files**: bank-switched ROM carts (Action Replay, Final Cartridge III, EasyFlash, Magic Desk, Ocean, Simons' BASIC, GMod2/3...), RAM/expansion carts (GeoRAM, REU, RAMCART), I/O-passthrough carts (IDE64, MMC64, RRNet). |
| This project | Generic/type-0 only (`src/c64/cartridge.py`) -- a single fixed 8K/16K ROM image, no bank-switching registers. Everything else raises `UnsupportedCartridge` with a specific reason. |
| Status | Already documented in `docs/cartridge.md`'s known-gaps list (no Ultimax, no bank-switching types, no RAM/Flash chip types, single-bank only). This was an explicit, deliberate scoping decision made *this session*, not an accidental omission. |
| Real-world impact | The widest gap by sheer count of unsupported types, but of the 111, the ones likely to matter for real games are the common bank-switched ROM formats (Magic Desk, Ocean type, EasyFlash) used by later/larger commercial titles -- simple 8K/16K games (the two already tested, Galaxian and Frogger) are unaffected. |
| Battle it? | Only if/when a specific desired cartridge dump turns out to need one of these -- add that one hardware type, not all 111. |

## VIC-II

| | |
|---|---|
| VICE | `vicii-fetch.c` steals real CPU cycles for both badlines *and* per-sprite DMA fetches (`dma_maincpu_steal_cycles`) -- the same mechanism, badlines and sprites both cost cycles. |
| This project | `is_badline` models the badline *condition* (unit-tested, including the DEN-latch quirk) but nothing ever spends the cost against the CPU. Sprite DMA is rendered with **zero CPU-timing cost** at all -- already noted in `docs/vic-ii.md`'s own text ("sprite DMA isn't cycle-costed at all"), just not broken out as its own bullet. |
| Status | Already documented as part of the umbrella "no real per-scanline rendering / nothing interleaves CPU and VIC-II cycle-by-cycle" gap -- not a separate category, the same root cause as the already-confirmed Frogger raster-split limitation. |
| Real-world impact | Real but subsumed: any game/demo whose main-loop timing budget assumes sprites cost cycles (common) is affected by the same underlying gap already named, not an additional one. |
| Battle it? | Same answer as the existing per-scanline gap in `docs/vic-ii.md`: a substantial architecture change (real cycle-interleaved CPU+VIC-II), deliberately deferred, not a quick fix. |
| Light pen (`$D013`/`$D014`) | Already documented as "not modeled." VICE implements it, but it needs actual light-pen input hardware this project has no path to. Correctly low priority -- confirmed, not a new finding. |

## SID

| | |
|---|---|
| Combined waveforms | reSID (`wave.cc`/`wave.h`) uses **4096-entry, per-chip-model (6581 vs 8580) lookup tables populated by sampling real silicon**, not a formula -- plus chip-specific shift-register "pre-writeback" quirks. Already documented here as "not modeled... standard AND-based simplification, not a claim of accuracy." **NEW precision**: this can't be closed by a better algorithm -- it requires vendoring reSID's actual sample tables, which is a licensing question (this project's GPL discipline in `docs/testing-strategy.md`), not a coding one. Real-world impact: audible timbre differences in SID music using combined pulse+triangle/sawtooth, and the noise-lockup trick some routines rely on -- not correctness-breaking, games still play. |
| ADSR rate tables | **Already correct, confirmed against reSID's own source** (`envelope.h`'s exact zone boundaries/periods) -- see the update just made to `docs/sid.md`, which previously over-hedged this as "not independently re-verified." Not a gap. |
| Digi-playback (volume-register sample trick) | **NEW finding**: untested, unverified either way whether it would work here -- see the note just added to `docs/sid.md`'s Known Gaps. Real but niche impact (a specific subset of music/SFX routines). |
| Filter | Already documented accurately as "not remotely reSID-grade." **NEW precision**: reSID's model is derived from a specific two-integrator-loop biquad circuit confirmed by SID co-designer Bob Yannes, using per-chip nonlinear DAC/inverter tables from die photographs -- categorically different from this project's generic digital Chamberlin filter, not just less precise. Confirms the existing doc's honesty rather than changing the assessment. |
| Battle it? | Combined waveforms and the filter are both real, audible gaps but both require vendoring reSID data/logic under a license this project has deliberately chosen not to take on (see `docs/testing-strategy.md`) -- not worth relitigating unless that license stance changes. Digi-playback is worth a cheap verification test (feed a synthetic volume-register ramp through `output_sample()` and listen/measure) before deciding whether it needs work. |

## Net recommendation

Of everything above, exactly two items are genuinely actionable without
either a large architecture change or a license decision this project has
already deliberately declined:

1. **Illegal-opcode failure mode**: change `IllegalOpcodeError` from an
   uncaught crash to a caught, logged skip, so an unanticipated real
   cartridge degrades instead of killing the process. Small, contained
   change.
2. **SID digi-playback**: write one diagnostic test to check whether
   rapid `$D418` writes through the existing per-sample tick model
   produce a recognizable waveform, before deciding whether it needs
   dedicated support.

Everything else surfaced here is either already an explicitly-scoped,
deliberate decision (cartridge hardware-type breadth, the CIA/PLA
simplifications) or subsumed by the single largest already-known gap
(real cycle-accurate CPU+VIC-II interleaving, i.e. per-scanline
rendering) -- which remains a substantial, deliberately-deferred
architecture change, not a set of independent smaller gaps to pick off
one at a time.
