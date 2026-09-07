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
  cia.md                # CIA register map + behavior (Phase 3)
  vic-ii.md             # VIC-II register map, text mode, sprites (Phase 4/5)
  sid.md                # SID register map + behavior (Phase 6)
  machine.md             # how Machine.step() wires everything together,
                        # incl. IRQ/NMI delivery (Phase 7)
scripts/
  fetch_dormann_tests.sh # fetches the GPLv3 Klaus Dormann suite, not vendored
  stage_roms.sh          # stages the user's own local C64 ROMs into
                          # gitignored roms/c64/ -- never downloads ROMs
                          # itself, see Phase 1 below
  render_frame.py        # boots the staged ROMs and writes a PNG of the
                          # VIC-II's screen output (Phase 4)
  render_audio.py        # plays a test tone through the real SID stack
                          # and writes a WAV file (Phase 6)
  run_c64.py             # boots the staged ROMs; screen+keyboard+audio,
                          # --type-file / Ctrl+V program input (Phase 8-10)
examples/
  sound_test.bas          # plays a scale on SID voice 1
  sprite_test.bas         # a bouncing sprite -- see run_c64.py --type-file
src/
  c6502/                # ported CPU core + assembler -- see "What came over" above
    emulator/
    asm/
  c64/                  # <-- the actual point of this repo. Zero runtime deps.
    bus.py                # the real C64 memory map + bank-switching (Phase 2)
    cpu_port.py            # the 6510's $00/$01 I/O port (Phase 2)
    cia.py                 # MOS 6526 CIA: ports, timers, TOD, ICR (Phase 3)
    keyboard_matrix.py      # 8x8 key matrix + CIA1 port coupling (Phase 3)
    joystick.py             # digital joystick (Phase 3)
    vic_ii.py               # MOS 6567/6569 VIC-II: registers + text-mode
                             # rendering + sprites/collisions (Phase 4/5)
    sid.py                  # MOS 6581/8580 SID: oscillators, ADSR,
                             # filter (Phase 6)
    machine.py              # ties CPU+Bus+chips together, real cycle
                             # driving + interrupt delivery (Phase 7)
  peripherals/          # real-world I/O bridges -- needs the "peripherals"
                        # extra (pygame); the only part of this repo with
                        # a runtime dependency.
    screen.py              # pygame window showing VicII output (Phase 8)
    keyboard.py            # real key events -> KeyboardMatrix (Phase 9)
    audio.py               # Sid.output_sample() -> pygame.mixer (Phase 10)
    auto_type.py            # reliable frame-timed program input (--type-file/Ctrl+V)
tests/
  emulator/             # CPU core tests (ported)
  asm/                  # assembler tests (ported, one adapted)
  peripherals/          # Screen + Keyboard + Audio + AutoTyper tests -- gated behind pytest.importorskip
  c64/                  # Bus + CpuPort + CIA + keyboard/joystick + VIC-II + SID + Machine tests
```

## Status / roadmap

See [docs/roadmap.md](docs/roadmap.md) for the detailed phase checklist.
Summary:

- [x] **Phase 0** — ported the CPU core + assembler from `c-compiler-6502`
- [x] **Phase 1** — ROM licensing research: VICE's "blanket permission"
      story is unverified lore, not a real license (confirmed via
      Debian's own dfsg-stripped `vice` package and outside research); this
      repo never fetches/vendors the original ROMs, `scripts/stage_roms.sh`
      only stages ROMs the user already has locally into gitignored
      `roms/c64/` — see `docs/roadmap.md`'s Phase 1 for the full writeup
- [x] **Phase 2** — the real C64 memory map + bank-switching `Bus`
      (`src/c64/bus.py`, `src/c64/cpu_port.py`) — verified against the
      user's actual staged ROMs, boots to the genuine KERNAL reset routine
      with zero CPU core changes; see `docs/roadmap.md`'s Phase 2
- [x] **Phase 3** — CIA 1 & 2 (`src/c64/cia.py`, `keyboard_matrix.py`,
      `joystick.py`) — ports, timers, TOD clock, ICR, keyboard/joystick
      coupling; verified against the real KERNAL, which initializes
      CIA1/CIA2 exactly as documented when run unmodified; see
      `docs/roadmap.md`'s Phase 3 and `docs/cia.md`
- [x] **Phase 4** — VIC-II, text mode only (`src/c64/vic_ii.py`) — the
      VIC-II's own bank-switched memory view (`Bus.read_vic`), standard
      character-mode rendering; verified by running the real KERNAL+BASIC
      unmodified and rendering the result: it produces the exact, iconic
      real C64 boot screen (`**** COMMODORE 64 BASIC V2 ****` etc.) from
      genuine ROM content; see `docs/roadmap.md`'s Phase 4 and
      `docs/vic-ii.md`
- [x] **Phase 5** — VIC-II sprites (fetch/render/expansion/multicolor/
      priority, sprite-sprite & sprite-background collision) — verified
      with a real assembled 6502 program via this project's own
      assembler; cycle-accurate raster/badline timing genuinely
      **not achieved** (needs a real interleaved CPU+VIC-II running
      machine that doesn't exist yet — badlines are modeled only as a
      queryable condition); see `docs/roadmap.md`'s Phase 5 and
      `docs/vic-ii.md`
- [x] **Phase 6** — SID (`src/c64/sid.py`) — three oscillators, ADSR
      envelopes, hard sync, ring modulation, a simple digital filter
      (explicitly not reSID's transistor-level model); verified with a
      real assembled 6502 program (`scripts/render_audio.py`) whose
      generated audio measured **exactly 440.0Hz** by zero-crossing count
      for a 440Hz note poke — see `docs/roadmap.md`'s Phase 6 and
      `docs/sid.md`. All six original roadmap phases are now done.
- [x] **Phase 7** — the real machine (`src/c64/machine.py`) — `Machine`
      drives CPU+Bus+both CIAs+VIC-II+SID together from real elapsed
      cycles, with real IRQ (level-triggered) and NMI (edge-triggered)
      delivery; verified by booting the real KERNAL+BASIC and watching
      its own real jiffy-clock counter (`$A0`-`$A2`) actually increment
      once BASIC reaches its keyboard-wait loop — see `docs/roadmap.md`'s
      Phase 7 and `docs/machine.md`.
- [x] **Phase 8** — screen output (`src/peripherals/screen.py`,
      `scripts/run_c64.py`) — pygame (this project's first runtime
      dependency, via the new `peripherals` extra — the emulation core
      stays dependency-free) displays `VicII.render_frame()` in a real
      window, paced to ~50Hz; verified by running the real KERNAL+BASIC
      through the actual `Screen.draw()` pipeline and confirming the
      real boot screen renders correctly — see `docs/roadmap.md`'s
      Phase 8. **Confirmed working on the user's real display** — ran
      `scripts/run_c64.py` and reported it worked (visually slow, since
      no speed-optimization pass has been done — see `docs/machine.md`'s
      profiling numbers and the `enable_audio` fix that already
      addressed the biggest identified waste).
- [x] **Phase 9** — keyboard input (`src/peripherals/keyboard.py`) — real
      pygame key events mapped to `KeyboardMatrix`. The keyboard-matrix-
      layout ambiguity `docs/cia.md` flagged as an open gap is now
      **resolved empirically**: pressed each of the 64 positions alone
      against the real staged KERNAL and read back the actual character
      via its own `GETIN` routine, rather than trusting either disputed
      community source (and caught a real error in one of them along the
      way) — see `KeyboardMatrix.KEY_POSITIONS` in `src/c64/
      keyboard_matrix.py` and `docs/cia.md`. Verified end-to-end: typing
      `HELLO`+`RETURN` via simulated key events through the real
      KERNAL+BASIC produces the exact real response
      (`?SYNTAX  ERROR`) — see `docs/roadmap.md`'s Phase 9.
- [x] **Phase 10** — audio output (`src/peripherals/audio.py`) — `Sid.
      output_sample()` fed to pygame's mixer, sampled once every real
      PHI2-cycles-per-sample period so pitch is genuinely correct
      regardless of host speed; verified end-to-end through the actual
      `Machine`+`AudioOutput` pipeline (not direct `Sid` calls) at
      **exactly 440.0Hz** for a real 440Hz note poke. Honest caveat, not
      swept under the rug: no wall-clock pacing was added, because
      profiling shows this project's core runs *slower* than real time
      once audio's on — pacing wouldn't fix that, a speed effort would,
      and one was already explicitly deferred once (Phase 8). Sustained
      playback can have audible gaps under load as a documented
      consequence — see `docs/roadmap.md`'s Phase 10.
- [x] **Reliable program input** (`src/peripherals/auto_type.py`,
      `examples/*.bas`) — raised before Phase 11 after live keyboard
      typing turned out to be less than rock solid; root cause was
      `run_c64.py`'s event loop only draining keyboard events once per
      simulated frame, so a fast real keypress can land entirely within
      one frame and never reach the emulated KERNAL. `AutoTyper` types by
      holding each key for a fixed number of PHI2 cycles, wired up via
      `run_c64.py --type-file` and Ctrl+V (real clipboard, via
      `pygame.scrap`, verified against a live X11 clipboard). **First
      landing measured at ~1 char/sec in practice — caught, diagnosed,
      and actually fixed, not excused**: the main loop now fast-forwards
      through typing (skips per-step render/audio, the dominant cost),
      and the hold/gap durations were re-measured against the real
      KERNAL's own `GETIN` instead of guessed, cutting them from
      ~78,624 cycles to a verified-reliable ~8,000/20,000. Result,
      measured on the real `sound_test.bas`: **920ms/char → 53.8ms/char
      (~17x)**. Also caught a real bug before shipping (`<`/`>`/`?`
      missing from the character table, silently corrupting real BASIC)
      and, while verifying the two example programs by actually running
      them, a real bug in the example program itself (not the emulator)
      — see `docs/roadmap.md`'s post-Phase-10 addendum.
- Next up: storage (Phase 11)

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

The emulation core (`src/c64/`, `src/c6502/`) has no compiled/native or
runtime dependencies at all -- that's still true. `src/peripherals/`
(real screen/keyboard/audio/disk I/O, Phase 8 onward) is the one
exception: it needs this project's `peripherals` extra (currently
pygame). Its tests (`tests/peripherals/`) are gated behind
`pytest.importorskip(...)`, so the base suite still passes with nothing
but `pytest` installed. `pyproject.toml` sets `pythonpath = ["src"]` so
`pytest` finds the packages directly from source; `pip install -e
".[dev]"` (add `,peripherals` to also exercise `src/peripherals/`) is
convenient for an interactive `python3` shell but not required just to
run the core tests.

```
pytest                            # fast suite
scripts/fetch_dormann_tests.sh    # one-time per machine
pytest -m slow                    # re-validates the ported CPU core
```
