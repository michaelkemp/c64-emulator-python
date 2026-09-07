# Roadmap / status

Detailed phase checklist for this project. Keep this file up to date as
work progresses — it's the answer to "where are we up to?" `CLAUDE.md`
links here and carries only the summary.

## Phase 0 — Ported from c-compiler-6502 (done)

- [x] NMOS 6502 CPU core (`src/c6502/emulator/`) — registers, flags, all
      legal addressing modes, 151-entry opcode dispatch table, cycle
      counting, reset/IRQ/NMI/BRK, a step trace formatter. Already passed
      Klaus Dormann's functional test suite in the source repo
      (30,646,177 steps, traps at the documented success address `$3469`)
      — re-validate here with `scripts/fetch_dormann_tests.sh && pytest -m
      slow`.
- [x] 6502 assembler (`src/c6502/asm/`) — two-pass label/forward-reference
      support, `.org`/`.byte`/`.word`/`.res` + equates, opcode encoding
      derived from the CPU's own `OPCODES` table (can't drift out of
      sync with what the CPU decodes).
- [x] Full test suites for both, ported unchanged (one test adapted —
      `tests/asm/test_assemble_program.py` no longer depends on the
      source repo's `Machine`/`AciaDevice`, which didn't come along; it
      now asserts on memory contents directly instead of console output).
- [x] `docs/6502-reference.md` — condensed ISA notes, ported as-is.

**Not ported, deliberately** (see `CLAUDE.md` for the full reasoning):
the source repo's `Bus`/`AciaDevice`/`Machine`/`run.py` (a serial-console
system built for *its own* custom board, not the C64's real hardware),
its `cc/` C-compiler stub (a different project's goal), its `msbasic/`
BASIC port and hardware-build docs (specific to that board).

## Phase 1 — ROM licensing research (resolved)

- [x] Verify whether VICE's inclusion of the original Commodore ROMs
      (citing a commonly-referenced "blanket permission" from Commodore)
      is backed by an actual primary source, or just community lore. —
      **Just lore.** Debian/Ubuntu's own `vice` package (`3.7.1+dfsg1`)
      strips the ROMs from the source entirely — the `+dfsg1` suffix means
      exactly that, and its shipped `/usr/share/doc/vice/copyright` says so
      outright. Its `README.ROMs` names the actual copyright holder
      ("Tulip Computers, in the Netherlands... being somewhat persnickety
      about who uses them"), not a grant of permission. External research
      agrees: the "Commodore gave permission" story traces to an
      unverifiable usenet post, never a real license grant — the same
      shape of unverified claim this project already burned itself on once
      with `msbasic` (see below).
- [x] Evaluate the clean-room open-source alternatives: MEGA65's "Open
      ROMs" project and "Pascual's BASIC" — check their actual license
      terms and current completeness/compatibility. — `MEGA65/open-roms`'s
      actual `LICENSE` file (fetched and read, not inferred from its
      README) is LGPLv3+, with per-file MIT notices on the BASIC portions
      mechanically derived from Microsoft's own `BASIC-M6502` source —
      genuinely verifiable, unlike VICE's ROM story. Its current C64
      completeness/compatibility hasn't been evaluated yet — do that
      before depending on it for anything beyond reference. "Pascual's
      BASIC" is described the same way (clean-room KERNAL, MS-derived
      BASIC) in community discussion, but no confirmed repo/license was
      found this session — verify its actual license file yourself before
      relying on it, same rule as everything else here.
- [x] Decide: vendor a clean-room replacement, or treat ROM acquisition as
      the *user's own* responsibility. — **The user's own responsibility.**
      This repo never fetches or vendors the original Commodore ROMs.
      `scripts/stage_roms.sh` copies ROMs the user already has locally
      (e.g. from installing VICE, whose ROM pack ends up under
      `~/.local/share/vice/C64` or `/usr/lib/vice/C64`) into this repo's
      already-gitignored `roms/c64/` — it never downloads anything itself.
      Point it at a different directory (`scripts/stage_roms.sh
      /path/to/your/roms`) if your ROMs live somewhere else, e.g. dumped
      from real hardware.
- [x] Document it here and in `docs/testing-strategy.md`. — done in both;
      see the "License discipline" section there for the ROM-specific
      rule.

## Phase 2 — C64 memory map + Bus (done)

- [x] `src/c64/bus.py` implementing the real C64 memory map: RAM, the
      BASIC/KERNAL/character ROMs overlaid via bank-switching (writes
      always land in the RAM underneath a ROM overlay; only reads see the
      overlay — see the module docstring for the full bank-switching
      table and reasoning), and the VIC-II/SID/CIA/color-RAM register
      windows. The three chip windows take an optional
      `read_register`/`write_register` object each and default to open
      bus (`0xFF`, writes ignored) since none of those chips exist yet
      (Phases 3/4/6) — `Bus` is fully testable on its own in the meantime.
      Color RAM (real 4-bit-wide SRAM, not a chip) is modeled directly.
- [x] `src/c64/cpu_port.py` — the 6510's I/O port at `$00`/`$01`
      (LORAM/HIRAM/CHAREN bank-switching bits, plus the rest of the port
      which nothing needs yet) as a memory-mapped device `Bus` dispatches
      to, **not** a change to the ported CPU core (confirmed design
      decision — see `CLAUDE.md`).
- [x] `tests/c64/` — unit tests for both, plus an integration sanity check
      (not committed as a test, just run manually this session): loading
      the user's actual staged ROMs (`roms/c64/`, via
      `scripts/stage_roms.sh`) into a real `Bus` + the ported `CPU` and
      calling `cpu.reset()` lands `PC` at `$FCE2` executing `LDX #$FF; SEI;
      TXS` — the real, documented start of the genuine KERNAL reset
      routine, fetched with zero CPU core changes.

## Phase 3 — CIA 1 & 2 (done)

- [x] `src/c64/cia.py` — `CIA6526`: both ports (with a pluggable
      `port_coupler` for cross-port electrical coupling, e.g. the
      keyboard matrix), Timer A/B (16-bit counter+latch, one-shot vs
      continuous, force-load strobe, Timer B counting Timer A's
      underflows), the TOD clock (BCD, latch-on-read-hours,
      stop-on-write-hours/restart-on-write-tenths, alarm), the interrupt
      control register (destructive read, set/clear-mask write), and a
      simplified serial data register. See `docs/cia.md` for the full
      behavior spec and known gaps (CNT pin, real serial timing, nothing
      yet drives real elapsed time or wires `irq_line` to the CPU).
- [x] `src/c64/keyboard_matrix.py` — `KeyboardMatrix` (bidirectional 8x8
      matrix sensing) and `Cia1Ports` (combines the matrix with up to two
      `Joystick`s into CIA1's `port_coupler`). No symbolic key-name table
      yet — see `docs/cia.md`'s gap note (two community references
      disagree on the exact layout; resolving it against the real KERNAL
      ROM's own table is left for whoever wires up real keyboard input).
- [x] `src/c64/joystick.py` — `Joystick`, digital up/down/left/right/fire.
- [x] `tests/c64/` — unit tests for all of the above, plus a real
      integration check (run manually this session, not committed as a
      test): wiring `CIA6526` into `Bus` at `$DC00`/`$DD00` alongside the
      genuine staged KERNAL and running ~200,000 real instructions shows
      the actual reset routine initializing CIA1's DDRA/DDRB exactly as
      documented (keyboard row-select output / column-sense input),
      resetting then correctly re-enabling Timer A's ICR bit, starting
      Timer A (the real jiffy-clock IRQ source), and initializing CIA2's
      DDRA to the well-documented `$3F` (VIC bank select + serial bus) —
      all from unmodified ROM code, none of it hand-tuned to match.
- [x] **`docs/cia.md`** — register map + behavior, written before the
      code, per `CLAUDE.md`'s documentation convention.
- Reference: MOS 6526 CIA preliminary datasheet —
  [6502.org](https://6502.org/documents/datasheets/mos/mos_6526_cia_preliminary_nov_1981.pdf).

## Phase 4 — VIC-II, text mode only (not started)

- [ ] Just enough to get BASIC's screen visible: standard character mode,
      the video matrix/color RAM relationship, border/background colors.
      Deliberately *not* cycle-accurate yet (no badlines, no sprite
      timing) — get something on screen before chasing timing precision.
- [ ] **`docs/vic-ii.md`** — start it here (register map, text-mode
      behavior); it'll grow in Phase 5 rather than becoming a second file.
- Reference: Christian Bauer's cycle-by-cycle reverse-engineering
  article — [cebix.net/VIC-Article.txt](https://www.cebix.net/VIC-Article.txt)
  — plus the official preliminary MOS 6567 datasheet —
  [6502.org](https://6502.org/documents/datasheets/mos/mos_6567_vic_ii_preliminary.pdf).

## Phase 5 — VIC-II sprites + cycle-accurate timing (not started)

- [ ] Sprite fetch/display, sprite-sprite and sprite-background collision
      detection, "badlines" (the VIC-II stealing cycles from the CPU to
      fetch video matrix data), and raster-IRQ timing precise enough for
      real software (much C64 software, especially anything from the
      demoscene, depends on exact raster timing).
- [ ] Extend `docs/vic-ii.md` (from Phase 4) with sprite/badline/raster
      timing behavior.

## Phase 6 — SID (not started)

- [ ] Waveform generators, ADSR envelopes, ring modulation, sync. The
      hardest part is the analog filter (even real 6581 chips vary
      unit-to-unit) — start with a reasonable digital approximation and
      refine later; this is the most forgiving chip to get "close enough"
      early, unlike VIC-II timing.
- [ ] **`docs/sid.md`** — register map + behavior, including which parts
      are an approximation vs. bit-accurate, per `CLAUDE.md`'s
      documentation convention.
- Reference: [reSID](https://github.com/daglem/reSID) — the standard
  reference implementation (GPL-licensed — study the analog-filter
  modeling approach, don't copy code; same discipline as this project's
  ported Klaus Dormann precedent).
