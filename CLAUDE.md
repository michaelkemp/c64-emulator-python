# c64-emulator-python

## Goal

Build a Python emulator for the **Commodore 64**: the real memory map
(including bank-switching), the VIC-II video chip, the SID sound chip,
and the two CIA I/O chips — enough to boot the real BASIC/KERNAL and run
real C64 software.

**This is explicitly not a C compiler project.** That work continues in
the sibling repo,
[github.com/michaelkemp/c-compiler-6502](https://github.com/michaelkemp/c-compiler-6502)
— if you find yourself wanting to build a C compiler, an assembler beyond
what's already ported here, or a custom (non-C64) hardware target, that
work belongs there, not here. The split exists specifically so the two
projects don't get tangled together.

**This file is the living source of truth**: goals, decisions, and
current status. Detail lives in [docs/](docs/); update both as decisions
change — same convention as the sibling repo.

## Where this started

The 6502 CPU core and assembler in `src/c6502/` were **ported unchanged**
from `c-compiler-6502`, where they were built from scratch and validated:
- The CPU core passed **Klaus Dormann's functional test suite** (the
  standard 6502 correctness gate) — 30,646,177 steps, traps at the
  documented success address `$3469`. Re-run this here with
  `scripts/fetch_dormann_tests.sh && pytest -m slow` to confirm the port
  didn't break anything.
- The assembler's opcode encoding is derived by inverting the CPU's own
  `OPCODES` table, so it can never drift out of sync with what the CPU
  actually decodes.

**Treat both as finished, trustworthy infrastructure** — the interesting,
unstarted work in *this* repo is everything C64-specific (`src/c64/`),
not the CPU core or assembler. Don't redesign or "improve" the ported
code without a concrete C64-specific reason; if something about it seems
wrong, check the sibling repo's own `docs/` first (especially
`docs/6502-reference.md`, ported as-is into this repo too) — it's
probably a deliberate, documented decision.

## What came over, and what didn't (and why)

**Ported as-is**:
- `src/c6502/emulator/{cpu,addressing,instructions,opcodes,trace,vectors}.py`
  — the CPU core.
- `src/c6502/emulator/bus.py` — **only** `FlatMemory` (a flat 64KB RAM,
  used for CPU-in-isolation testing and the Dormann suite). The sibling
  repo's `Bus` class implemented *its own* custom RAM/ROM/ACIA memory map
  — not the C64's — so it didn't come along. The real C64 memory map is
  this repo's own Phase 2 (`docs/roadmap.md`), to be built fresh in
  `src/c64/`.
- `src/c6502/asm/*` — the whole assembler, unchanged. General-purpose,
  not tied to any particular memory map.
- All CPU-core and assembler tests (`tests/emulator/`, `tests/asm/`),
  unchanged except `tests/asm/test_assemble_program.py` (see its own
  docstring — it used to prove the assembler end-to-end via the sibling
  repo's `Machine`/serial console, which doesn't exist here; it now
  asserts on memory contents directly instead).
- `docs/6502-reference.md` — condensed 6502 ISA notes.
- `scripts/fetch_dormann_tests.sh`.

**Deliberately not ported** (don't re-introduce these without a reason
specific to *this* project):
- `AciaDevice`/`Machine`/`run.py` — a serial-console system built for the
  sibling repo's own custom breadboard computer. The C64 has its own,
  completely different I/O story (VIC-II for video, CIA for keyboard) —
  build that fresh in `src/c64/`, don't adapt the ACIA code.
- `src/c6502/cc/` — the sibling repo's C-compiler stub. Out of scope here
  entirely.
- `msbasic/` and its fetch/build scripts — a Microsoft BASIC port built
  for the sibling repo's *own* memory map and serial ACIA. The C64's
  BASIC is a completely different ROM with its own (real, historical)
  hardware interface — see "ROM licensing" below, not this.
- The sibling repo's hardware-build docs (`docs/hardware-path.md`,
  `docs/hardware-build.md`, `docs/hardware/`) — about building *that*
  project's own custom breadboard computer. Not relevant to emulating an
  existing historical machine.

## Key decisions carried over as guidance (not just code)

- **The C64 uses a 6510, not a plain 6502** — the only real difference is
  a 2-bit I/O port at `$00`/`$01` (bank-switching + a couple of control
  lines). Model this as a memory-mapped device on the C64's own `Bus`,
  **not** a change to the ported CPU core — the two zero-page addresses
  are just another region a `Bus.read8`/`write8` dispatches to, the same
  pattern the sibling repo already used for its ACIA. This means the
  ported CPU core needs zero modification for the C64's CPU to work
  correctly.
- **License discipline** — see `docs/testing-strategy.md`'s "License
  discipline" section for the full rule and the mistakes it came from.
  Short version: never vendor third-party content without an
  actually-verified license (read the real license text, don't trust a
  README's claim); default to fetch-on-demand, gitignored. This applies
  directly to Commodore's ROMs (see Phase 1 below — genuinely
  unresolved, don't assume a path) and to reSID/VICE as reference
  material for the SID/general behavior (GPL — read for understanding,
  don't copy code).
- **The assembler's design quirks carry over as-is** — see its module
  docstrings (`src/c6502/asm/assembler.py` etc.) for things like the
  "labels always assemble as absolute addressing" simplification. Not
  re-explained here; the code and its own comments are the source of
  truth for how it behaves.

## Documentation convention: one reference doc per chip

`docs/6502-reference.md` documents the CPU core; the sibling repo's
`docs/architecture.md` documented the ACIA's register semantics straight
from its datasheet before any code was written against it. **Do the same
here for every custom chip, written as (or just before) it's implemented,
not after**: `docs/cia.md`, `docs/vic-ii.md`, `docs/sid.md`. Each should
cover the register map, the chip's actual documented behavior (cite the
datasheet/article section), and any deliberate simplification or known
gap versus real hardware — the same shape as the sibling repo's
`docs/6502-reference.md` and its `AciaDevice` documentation. A chip
implementation with no doc explaining its register semantics is exactly
the kind of undocumented decision this whole convention exists to avoid.
Each phase in `docs/roadmap.md` names the specific doc it owes.

## Repo map

```
CLAUDE.md              # this file
README.md              # short description + quickstart
pyproject.toml         # package metadata, dev dependencies (pytest)
docs/
  roadmap.md            # phase checklist / detailed status tracker
  6502-reference.md     # condensed 6502 ISA notes (ported as-is)
  testing-strategy.md   # how correctness gets validated, incl. license discipline
  cia.md, vic-ii.md, sid.md  # one per custom chip, written as each is
                             # implemented -- see "Documentation convention" above.
                             # Don't exist yet; nothing chip-specific is built yet.
scripts/
  fetch_dormann_tests.sh # fetches the GPLv3 Klaus Dormann suite, not vendored
src/
  c6502/                # ported CPU core + assembler -- see "What came over" above
    emulator/
    asm/
  c64/                  # <-- the actual point of this repo. Nothing here yet.
tests/
  emulator/             # CPU core tests (ported)
  asm/                  # assembler tests (ported, one adapted)
```

## Status / roadmap

See [docs/roadmap.md](docs/roadmap.md) for the detailed phase checklist.
Summary:

- [x] **Phase 0** — ported the CPU core + assembler from `c-compiler-6502`
- [ ] **Phase 1** — ROM licensing research (do this before any chip code —
      see `docs/roadmap.md`, this is genuinely unresolved, not a
      formality)
- [ ] **Phase 2** — the real C64 memory map + bank-switching `Bus`
- [ ] **Phase 3** — CIA 1 & 2 (keyboard, timers)
- [ ] **Phase 4** — VIC-II, text mode only (get BASIC's screen visible)
- [ ] **Phase 5** — VIC-II sprites + cycle-accurate raster timing
- [ ] **Phase 6** — SID

## Reference documentation

External sources of truth for the C64-specific chips (linked, not
vendored — pull specific facts as needed):

- VIC-II: Christian Bauer's cycle-by-cycle reverse-engineering article —
  [cebix.net/VIC-Article.txt](https://www.cebix.net/VIC-Article.txt) —
  plus the official preliminary MOS 6567 datasheet —
  [6502.org](https://6502.org/documents/datasheets/mos/mos_6567_vic_ii_preliminary.pdf).
- SID: [reSID](https://github.com/daglem/reSID) — the standard reference
  implementation (GPL — see "License discipline" above).
- CIA 6526: official preliminary datasheet —
  [6502.org](https://6502.org/documents/datasheets/mos/mos_6526_cia_preliminary_nov_1981.pdf).
- ROM licensing candidates to evaluate properly (see `docs/roadmap.md`'s
  Phase 1): VICE's own documentation (for the "blanket permission" claim
  — verify against a primary source, don't just repeat it), the MEGA65
  "Open ROMs" project, and "Pascual's BASIC" (a clean-room KERNAL/BASIC
  reimplementation) — search for these rather than trust any specific URL
  written down here, since none were verified as of this writing.

## Running tests

Same setup as the sibling repo — no compiled/native dependencies, no
runtime dependencies at all. `pyproject.toml` sets `pythonpath = ["src"]`
so `pytest` finds the packages directly from source; `pip install
-e ".[dev]"` is convenient for an interactive `python3` shell but not
required just to run tests.

```
pytest                            # fast suite
scripts/fetch_dormann_tests.sh    # one-time per machine
pytest -m slow                    # re-validates the ported CPU core
```
