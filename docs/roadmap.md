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

## Phase 4 — VIC-II, text mode only (done)

- [x] `src/c64/vic_ii.py` — `VicII`: the full register file (sprite
      registers stored but inert -- Phase 5), the `$D011`/raster-compare
      dual-purpose-bit quirk, the interrupt register's write-1-to-clear
      semantics (notably *not* the CIAs' read-clears-all), and standard
      character-mode rendering (`render_frame`) into an indexed pixel
      grid, honoring `DEN`/`RSEL`/`CSEL`/`XSCROLL`/`YSCROLL`.
- [x] `Bus.read_vic`/`Bus.vic_bank_base`/`Bus.read_color_nibble` — the
      VIC-II's own bank-switched view of memory (selected by CIA2, not
      the CPU's LORAM/HIRAM/CHAREN), including the hardwired character-ROM
      substitution at `$1000`/`$9000` in banks 0/2. See `docs/vic-ii.md`.
- [x] `tests/c64/test_vic_ii.py` plus `Bus` tests for the new memory-view
      methods, and a real integration check (run manually this session,
      not committed as a test): running the genuine KERNAL+BASIC ROMs
      unmodified for 3,000,000 instructions through the full
      CPU+Bus+CIA1+CIA2+VIC-II stack produces `$D011=$1B`,
      `$D018=$14` (matrix `$0400`, chars `$1000`), border color 14,
      background color 6 -- all the well-known real C64 defaults -- and
      `render_frame` of that state, saved as a PNG, shows the actual
      readable text `**** COMMODORE 64 BASIC V2 ****` /
      `64K RAM SYSTEM  38911 BASIC BYTES FREE` / `READY.`: the real,
      iconic C64 boot screen, from genuine ROM content, none of it
      hand-tuned to match.
- [x] **`docs/vic-ii.md`** — register map, the VIC-II's-own-memory-view
      explanation, and this phase's known gaps (no sprites/bitmap/ECM, not
      cycle-accurate, approximate border geometry and palette). Will grow
      in Phase 5.
- Reference: Christian Bauer's cycle-by-cycle reverse-engineering
  article — [cebix.net/VIC-Article.txt](https://www.cebix.net/VIC-Article.txt)
  — plus the official preliminary MOS 6567 datasheet —
  [6502.org](https://6502.org/documents/datasheets/mos/mos_6567_vic_ii_preliminary.pdf).

## Phase 5 — VIC-II sprites + cycle-accurate timing (sprites done; cycle-accurate timing deferred)

- [x] Sprite fetch/display: shape data via sprite pointers (the video
      matrix's last 8 bytes) through the same `Bus.read_vic` used for
      character data (so the char-ROM-substitution quirk applies to
      sprites too, correctly); standard and multicolor pixel decoding;
      X/Y expansion; the real X=24/Y=50 coordinate origin; sprite-vs-
      sprite priority by number and each sprite's own vs-display priority
      bit.
- [x] Sprite-sprite and sprite-background collision detection: `$D01E`/
      `$D01F` accumulate collisions across renders and clear-on-read (a
      different rule from `$D019`'s write-1-to-clear), firing `$D019`'s
      IMMC/IMBC only for genuinely new collisions so an ongoing overlap
      doesn't refire the interrupt every frame.
- [x] "Badlines" — but as a queryable condition only
      (`VicII.is_badline`, including the DEN-latched-at-line-`$30` quirk
      that the real "open border" demo trick depends on), **not** actual
      CPU-cycle stealing: that needs a real interleaved CPU+VIC-II main
      loop, which doesn't exist yet (see `docs/cia.md`'s `irq_line` gap —
      same missing piece). Tracked as a future milestone, not this phase.
- [ ] Raster-IRQ timing precise enough for real demoscene software —
      genuinely **not achieved**, and can't be until that same real
      running-machine milestone exists. Revisit when that milestone is
      built.
- [x] Extended `docs/vic-ii.md` (from Phase 4) with sprite/collision/
      badline behavior and an explicit account of what's still missing
      and why.
- Verified with a real integration check (run manually this session, not
  committed as a test): a tiny genuine 6502 program, assembled with this
  project's own ported assembler (`c6502.asm.assemble`) and run on the
  ported CPU core, pokes a sprite pointer, shape data, position, enable
  bit, and color directly into `Bus`/`VicII` — `render_frame` then shows
  the sprite rendered at exactly the expected pixel position.

**Post-Phase-5 addendum** (prompted by planning ahead for Phase 6's SID,
which has its own real PHI2 clock dependency): added `VicII.tick(cycles)`,
matching `CIA6526.tick(cycles)`'s shape, replacing the previous
"something external decides when to call `step_line()`" gap with a real
cycle-driven interface. Also settled and documented (`docs/vic-ii.md`'s
"Clock rate" section, verified via web search and cross-checked against
VICE's own local ROM database) that this project standardizes on **PAL**
timing (63 cycles/line, 312 lines/frame, 985,248 Hz) rather than either
NTSC variant. Verified by driving `VicII.tick()`/`CIA6526.tick()` with the
real `CPU.step().cycles` values while booting the actual KERNAL+BASIC for
3,000,000 instructions (~9.9M PHI2 cycles): the independently-computed
expected raster line (`total_cycles // 63 % 312`) matched
`VicII.current_raster` exactly, with the real boot screen still correct.
This does **not** change the "real cycle stealing" gap above — `tick()`
makes raster timing itself cycle-accurate, it doesn't make VIC-II able to
actually take cycles away from the CPU, which still needs the same
not-yet-built running-machine milestone.

## Phase 6 — SID (done)

- [x] `src/c64/sid.py` — `Sid`/`Voice`: three independent 24-bit-
      phase-accumulator oscillators (sawtooth/triangle/pulse/noise, with
      the standard AND-combination approximation for multiple waveform
      bits at once), hard sync and ring modulation via real cross-voice
      coupling (source order 1←3, 2←1, 3←2), a full ADSR state machine
      driven by the real MOS 6581 datasheet's rate tables (fetched and
      verified against a transcription of the actual datasheet, not
      recalled unchecked) with the commonly-published exponential
      decay/release zone approximation, `OSC3`/`ENV3` readback, voice 3
      disconnect, and a simple digital state-variable filter (explicitly
      *not* reSID's transistor-level model — see `docs/sid.md`).
      `Sid.tick(cycles)` matches `CIA6526.tick`/`VicII.tick`'s shape, per
      the addendum above.
- [x] **`docs/sid.md`** — register map + behavior, written before the
      code, with explicit callouts of every approximation vs. verified
      fact, per `CLAUDE.md`'s documentation convention.
- [x] `tests/c64/test_sid.py` — 22 tests covering register decode,
      each waveform, combined waveforms, hard sync, ring modulation,
      noise determinism, the full ADSR state machine (including the
      "re-gate while attacking doesn't reset to 0" real-hardware
      behavior), voice 3 disconnect, and filter parameter decode. Caught
      and fixed two real bugs while writing them: a fragile test margin
      that could bleed an attack-phase check into decay (fixed with an
      exact cycle count instead of an approximate one), and — more
      importantly — a genuine bug in `output_sample()` that centered the
      envelope-scaled level around the DC midpoint instead of centering
      the raw waveform first and scaling the result by envelope, which
      made every silent, untriggered voice contribute a spurious `-1.0`
      instead of true silence.
- Verified with a real integration check (run manually this session, not
  committed as a test, now reproducible via `scripts/render_audio.py`):
  a tiny genuine 6502 program, assembled with this project's own ported
  assembler and run on the ported CPU core, pokes a real SID voice's
  frequency register for 440Hz, triangle waveform, and gate directly.
  Driving `Sid.tick()`/`output_sample()` with the correct PAL-clock-to-
  44100Hz sample ratio and counting zero-crossings in the generated
  audio measured **exactly 440.0Hz** — from genuine register pokes by
  real 6502 code, none of it hand-tuned to match.
- Reference: [reSID](https://github.com/daglem/reSID) — the standard
  reference implementation (GPL-licensed — study the analog-filter
  modeling approach, don't copy code; same discipline as this project's
  ported Klaus Dormann precedent). Not used as a source of any code or
  exact constants here -- see `docs/sid.md` for what was actually
  verified against the primary MOS 6581 datasheet instead.

## Phase 7 — The real machine (done)

With all six chips built, this closes the loop every prior phase's docs
flagged as missing: something that actually runs the CPU and every chip
together from real elapsed cycles, with real interrupt delivery.

- [x] `src/c64/machine.py` — `Machine`: owns `Bus`, `CPU`, both
      `CIA6526`s, `VicII`, `Sid`, the keyboard matrix, and both
      joysticks. `step()` executes one CPU instruction, feeds its exact
      cycle count to every chip's `tick()`, then delivers interrupts —
      IRQ level-triggered (`cia1.irq_line or vic.irq_line`, checked every
      step, safe to call repeatedly since the ported CPU's own `irq()`
      already no-ops while the I flag is set), NMI edge-triggered
      (`cia2.irq_line`'s rising edge only, matching real 6502 semantics).
      `from_roms()` is a convenience constructor loading the three
      staged ROM files. See `docs/machine.md` for the full design and
      known gaps (still not cycle-exact within an instruction, badlines
      still don't steal cycles, nothing paces real wall-clock time yet —
      that's Phase 10's job once real audio exists).
- [x] **`docs/machine.md`** — written before the code, per `CLAUDE.md`'s
      documentation convention (extended here to the integration layer,
      not just individual chips, since the design decisions involved —
      level vs. edge-triggered interrupts, when cycles get spent — are
      exactly the kind this convention exists to make explicit).
- [x] `tests/c64/test_machine.py` — 8 tests, including two tiny genuine
      6502 programs (assembled with this project's own ported assembler)
      that prove real IRQ delivery from CIA1 and real edge-triggered NMI
      delivery from CIA2 (verifying it does **not** re-fire while the
      source line stays asserted without being cleared).
- Verified with a real integration check (run manually this session, not
  committed as a test): booting the genuine, unmodified KERNAL+BASIC
  through `Machine` for 1,000,000 instructions shows the KERNAL's own
  jiffy-clock counter (`$A0`-`$A2`, the real "TIME" counter every C64
  KERNAL maintains) staying at zero during the RAM-test/hardware-init
  phase (consistent with Phase 4's finding that the screen doesn't turn
  on until ~561,000 instructions), then actually incrementing once BASIC
  reaches its keyboard-wait loop (`$E5CD`) — concrete, unmodified-ROM
  proof that CIA1 Timer A underflow reaches `irq_line`, `Machine.step()`
  delivers it, the real KERNAL IRQ handler runs and does its real job,
  and execution correctly resumes afterward.

## Phase 8 — Screen output (done)

- [x] `src/peripherals/screen.py` — `Screen`: a pygame window displaying
      `VicII.render_frame()`, scaled and capped to ~50Hz. Lives in a new
      `src/peripherals/` package (a "peripherals" extra in
      `pyproject.toml` — `pip install -e ".[peripherals]"`), kept
      strictly separate from the emulation core in `src/c64/`, which
      still has zero runtime dependencies. **pygame** is this project's
      first-ever runtime dependency (user's choice — also covers keyboard
      events for Phase 9 and audio output for Phase 10, avoiding three
      separate libraries).
- [x] Real-time pacing "almost for free": `scripts/run_c64.py` runs the
      `Machine` for exactly one PAL frame's worth of cycles
      (`CYCLES_PER_FRAME`) between each display update, and caps the
      display to ~50Hz -- not the dedicated wall-clock pacing
      `docs/machine.md` still flags as missing (that's Phase 10, once
      real audio needs genuinely precise timing), but good enough to
      watch the screen update at approximately real C64 speed.
- [x] `tests/peripherals/test_screen.py` — 6 tests, run headlessly via
      SDL's dummy video driver (`SDL_VIDEODRIVER=dummy`, standard
      technique for testing pygame code without a real display), gated
      behind `pytest.importorskip("pygame")` so the base test suite
      still runs with zero dependencies installed. Caught a real bug:
      `pygame.transform.scale`'s in-place destination form requires the
      source and destination surfaces to already share a pixel format,
      which isn't guaranteed -- fixed by scaling to a new surface and
      blitting instead (blit converts formats automatically).
- Verified with a real integration check (run manually this session, not
  committed as a test, reproducible via `scripts/run_c64.py`): running
  the real KERNAL+BASIC through `Machine` for 160 simulated PAL frames
  and drawing each one through the actual `Screen.draw()` pipeline (not
  just the underlying pixel-index arrays `VicII.render_frame()` returns)
  produces the exact real C64 boot screen when saved and viewed -- this
  is the first phase whose validation exercises the literal code path
  the user runs, not just the underlying library.
- **The user will verify this one interactively** on their own machine
  (this development environment has no real display) -- run
  `scripts/run_c64.py` and confirm the window actually looks right.

## Phase 9 — Keyboard input (done)

- [x] Resolved the keyboard-matrix-layout ambiguity flagged in
      `docs/cia.md` **empirically**, not by trusting either disputed
      community source: for each of the 64 `(row, col)` positions, pressed
      it alone, ran `Machine` far enough for the real IRQ-driven scan to
      see it, and called the actual KERNAL's own `GETIN` routine (`$FFE4`)
      to read back what character the genuine ROM decodes it to. Result
      is internally consistent (a QWERTY-shaped layout; exactly 4
      positions produce nothing — the real 4 modifier keys) and caught a
      real error in the `sta.c64.org` table it otherwise matches almost
      exactly (`(0,2)` is `CRSR RIGHT`, not `←`). Landed as
      `KeyboardMatrix.KEY_POSITIONS`/`press_key`/`release_key` in
      `src/c64/keyboard_matrix.py` (not `peripherals/`, since it's a fact
      about the matrix itself, not about bridging to real input) — see
      `docs/cia.md`.
- [x] `src/peripherals/keyboard.py` — `Keyboard`: real pygame key events
      mapped to the matrix. Handles the one real hardware quirk this
      needs: a modern keyboard's four separate arrow keys map onto the
      C64's two physical cursor keys (`CRSR_RIGHT`/`CRSR_DOWN`) plus a
      *synthesized* `LSHIFT` for Left/Up (real hardware reverses cursor
      direction via Shift) -- reference-counted, not a single flag, so
      releasing one arrow key can't force-release a real Shift the user
      is still physically holding, or a shift the *other* arrow key still
      needs. `RESTORE` (mapped to F12) isn't a matrix key on real
      hardware (see `docs/cia.md`) -- calls `Machine.cpu.nmi()` directly.
- [x] `scripts/run_c64.py` now routes pygame keyboard events to `Keyboard`
      alongside the existing screen loop.
- [x] `tests/peripherals/test_keyboard.py` — 8 tests. Caught a real
      design bug before it shipped: the initial single-flag design for
      the synthesized Shift would force-release a genuinely-held real
      Shift key when an arrow key was released; fixed with proper
      reference counting.
- Verified with a real integration check (run manually this session, not
  committed as a test): booting the real KERNAL+BASIC, then "typing"
  `HELLO` + `RETURN` entirely through simulated pygame key events (via
  `Keyboard`, through the real matrix, real CIA1, real KERNAL scan, real
  BASIC input handling) produces the exact real C64 response --
  `HELLO` echoed, `?SYNTAX  ERROR`, a fresh `READY.` -- rendered and
  confirmed via the actual `Screen` pipeline, the same standard of proof
  as every prior phase.

## Phase 10 — Audio output (done, with an honest caveat)

- [x] `src/peripherals/audio.py` — `AudioOutput`: feeds `Sid.output_sample()`
      to real audio output via pygame's mixer. `advance(cycles)` takes
      the exact same cycle count `Machine.step()` returns (same shape as
      `CIA6526.tick`/`VicII.tick`), accumulates PHI2 cycles, and samples
      `Sid` once every `cycles_per_sample` (`PAL_CLOCK_HZ` ÷ the output
      rate) -- so pitch is genuinely correct, tied to real emulated
      cycles rather than wall-clock time, regardless of how fast this
      process actually runs them. Chunks default to one video frame's
      worth of samples (`samples_per_frame`), queued/played on a
      `pygame.mixer.Channel`.
- [x] `scripts/run_c64.py` now enables audio by default (`--no-audio` to
      opt out) and calls `AudioOutput.advance()` alongside the existing
      per-frame `Machine.step()` loop.
- [x] `Machine` wall-clock pacing: **deliberately not built**, and said so
      plainly rather than silently skipped. The original plan (back when
      Phase 8 was scoped) assumed real-time pacing would be needed once
      audio existed; in practice, `docs/machine.md`'s own profiling shows
      this project's unoptimized pure-Python core runs *slower* than real
      time once SID ticking is on (the most expensive of the four ticked
      chips) -- so throttling *down* to real-time wouldn't help; the
      bottleneck is generation being too slow, not too fast. Consequence,
      stated honestly: sustained audio playback can have audible gaps
      under load on hardware this slow. A dedicated speed effort (already
      explicitly deferred once, in Phase 8) is what would actually fix
      this, not pacing logic.
- [x] `tests/peripherals/test_audio.py` — 5 tests, headless via SDL's
      dummy audio driver (`SDL_AUDIODRIVER=dummy`), gated behind
      `pytest.importorskip("pygame")`.
- Verified with a real integration check (run manually this session, not
  committed as a test): a tiny genuine 6502 program (this project's own
  assembler) pokes a real SID voice for a 440Hz note, run through the
  actual `Machine` + `AudioOutput` production pipeline (not direct `Sid`
  calls, unlike the Phase 6 check) -- zero-crossing counting on the
  captured samples measured **exactly 440.0Hz**.

## Phase 11 — Storage: disk + cartridge (not started)

- [ ] Decide fidelity level explicitly before starting: a real 1541
      emulation is itself another whole 6502+ROM+RAM machine talking a
      serial protocol (would reuse `c6502` a second time) — much bigger
      than a "fake fast-load" that intercepts KERNAL's LOAD routine and
      feeds bytes straight from a `.d64` file, which is what most
      simplified emulators actually do. Possibly split into both, in that
      order.
- [ ] Cartridge (`.crt`) support extends `Bus`'s existing bank-switching
      to handle the GAME/EXROM "ultimax" mode Phase 2 explicitly deferred.
- [ ] Blank/writable disk image creation, so software running in the
      emulator can actually save data back out to a real file (raised
      alongside the original `peripherals/` idea).
