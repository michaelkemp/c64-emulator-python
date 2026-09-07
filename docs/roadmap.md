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

## Phase 1 — ROM licensing research (not started, do this first)

Before writing any chip emulation, resolve how the BASIC/KERNAL/character
ROMs actually get into this project — don't assume either path without
checking:

- [ ] Verify whether VICE's inclusion of the original Commodore ROMs
      (citing a commonly-referenced "blanket permission" from Commodore)
      is backed by an actual primary source, or just community lore.
- [ ] Evaluate the clean-room open-source alternatives: MEGA65's "Open
      ROMs" project and "Pascual's BASIC" — check their actual license
      terms and current completeness/compatibility.
- [ ] Decide: vendor a clean-room replacement (if its license genuinely
      allows it), or treat ROM acquisition as the *user's own*
      responsibility (dump your own real C64's ROMs) the way VICE's
      upstream documentation describes for users who can't rely on the
      permission claim -- and never fetch/vendor the original Commodore
      ROMs ourselves without a verified legal basis.
- [ ] Whatever's decided, document it here and in `docs/testing-strategy.md`
      with the same rigor as this project's ported Klaus Dormann/msbasic
      precedent (GPLv3 suite: fetched on demand, never vendored, license
      corrected after actually reading `license.txt`; msbasic: fetched
      on demand despite a claimed permissive license, since no actual
      `LICENSE` file backed it up).

## Phase 2 — C64 memory map + Bus (not started)

- [ ] A `src/c64/bus.py` implementing the real C64 memory map: RAM, the
      BASIC/KERNAL/character ROMs (overlaid via bank-switching, not
      always visible at the same time), the VIC-II/SID/CIA/color-RAM
      register windows.
- [ ] The 6510's 2-bit I/O port at `$00`/`$01` (bank-switching + a couple
      of control lines) — model as a memory-mapped device this `Bus`
      dispatches to, **not** a change to the ported CPU core (confirmed
      design decision — see `CLAUDE.md`).

## Phase 3 — CIA 1 & 2 (not started)

- [ ] Keyboard matrix scanning (CIA1), joystick ports, timers (A/B modes,
      TOD clock), serial shift register, interrupt control register.
      Least exotic of the three custom chips — a reasonable first target
      after the memory map exists.
- Reference: MOS 6526 CIA preliminary datasheet —
  [6502.org](https://6502.org/documents/datasheets/mos/mos_6526_cia_preliminary_nov_1981.pdf).

## Phase 4 — VIC-II, text mode only (not started)

- [ ] Just enough to get BASIC's screen visible: standard character mode,
      the video matrix/color RAM relationship, border/background colors.
      Deliberately *not* cycle-accurate yet (no badlines, no sprite
      timing) — get something on screen before chasing timing precision.
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

## Phase 6 — SID (not started)

- [ ] Waveform generators, ADSR envelopes, ring modulation, sync. The
      hardest part is the analog filter (even real 6581 chips vary
      unit-to-unit) — start with a reasonable digital approximation and
      refine later; this is the most forgiving chip to get "close enough"
      early, unlike VIC-II timing.
- Reference: [reSID](https://github.com/daglem/reSID) — the standard
  reference implementation (GPL-licensed — study the analog-filter
  modeling approach, don't copy code; same discipline as this project's
  ported Klaus Dormann precedent).
