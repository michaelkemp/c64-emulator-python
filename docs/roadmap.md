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

## Phase 10 — Audio output (done; the original caveat below turned out to be two separate real bugs, both fixed)

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

**Post-Phase-10 addendum: PyPy adopted, then two more real bugs found by
actually listening to it.** The "sustained playback can have audible
gaps" caveat above was real, but PyPy (see `docs/machine.md`'s
Performance section: 6.7x-8.8x faster across real benchmarks, every test
passing identically, `pygame` included) fixed the raw-throughput half of
it -- yet a real `sound_test.bas` played through PyPy still came out as
short stuttering ticks, not one steady note. That turned out to be two
separate, genuine bugs, not a continuation of the same slowness:

1. **`AudioOutput` silently dropped chunks.** `pygame.mixer.Channel.
   queue()` has exactly one "next sound" slot -- calling it again before
   the previously-queued chunk is promoted to "currently playing"
   silently discards that chunk (confirmed empirically: `get_queue()`
   returns the second Sound, not the first, after queueing both
   back-to-back). The original `_flush_chunk` called `.queue()` the
   instant a chunk completed, with no check that the slot was actually
   free -- so any timing jitter around the real ~20ms/chunk cadence
   could drop a perfectly correct, on-time chunk. Measured directly
   against the real pipeline under real wall-clock pacing: 0 drops in 67
   chunks over 3s under CPython (computation itself was slow enough to
   never stress it) vs. 1 drop in 148 chunks over 3s under PyPy (once
   computation stopped being the bottleneck, real pacing exposed it
   immediately). Fixed with a proper FIFO (`AudioOutput._ready`,
   `_pump()`) that only hands a chunk to the mixer once its slot is
   confirmed empty -- chunks now wait safely in Python instead of being
   overwritten. New regression test
   (`test_a_chunk_completed_while_the_mixers_queue_slot_is_still_full_is_not_dropped`)
   verified to fail against the pre-fix code with the actual bug
   (`get_queue()` returns a different Sound object than the one that was
   still waiting) via `git stash`, not just an incidental error.
2. **`Screen`'s hardcoded `target_fps=50` doesn't match this project's
   own PAL constants.** `PAL_CLOCK_HZ / CYCLES_PER_FRAME` ≈ **50.1245Hz**
   (real PAL C64s do run slightly above 50Hz -- a correctly-cited fact,
   not this project's own rounding), not the flat 50.0 the loop was
   pacing to. A persistent, non-random ~0.25% mismatch: one loop
   iteration produces ~19.951ms of audio content but consumes a real
   20.000ms of wall-clock time, slowly starving the buffer over a
   sustained note independent of the drop bug above. Fixed by computing
   the exact rate from the existing constants instead of hardcoding it.

See `src/peripherals/audio.py` and `screen.py`'s module docstrings for
the full diagnosis.

**Post-Phase-10 addendum: the actual staccato/"morse code" sound wasn't
either of the two bugs above -- it was `sound_test.bas`'s own ADSR
settings, and the emulator was correct the whole time.** Re-confirmed by
ear once PyPy was in use: still choppy, so the two fixes above -- real
bugs, both worth keeping -- were not the actual cause of the originally-
reported symptom. Built `examples/sid_diagnostic.bas` (types through
every voice x every waveform, including noise, printing which combo is
playing before each) specifically to isolate whether it was a
voice/waveform-specific bug; instrumenting the real `Voice.envelope`
value directly during actual playback (not guessing) found the answer:
`sound_test.bas` set `release=8` (`POKE 54278,248` -- sustain=15,
release=8), a real SID rate meaning ~300ms nominal to decay from 255 to
0 -- but the BASIC delay loop between notes (`FOR D=1 TO 100: NEXT D`)
only lasts **~190ms of real emulated time** (BASIC V2's famously slow,
floating-point-based `FOR...NEXT` really is that slow on real hardware
too, confirmed by directly measuring: ~1470-1900 cycles per empty
iteration). Measured directly: envelope was still at **92 out of 255**
(~36%) when the next note's near-instant 2ms attack snapped it back to
full volume -- a real, audible partial dip-and-recover on every single
note, which is exactly what a recorded waveform (a real Audacity capture
of the actual speaker output, not a simulation) visually confirmed:
distinct amplitude blips separated by shallow dips, not one continuous
tone -- "like morse code," in the user's words, matching the screenshot
exactly. A real, physical C64 running this exact program with these
exact register values would sound identically choppy -- **this specific
symptom (the release-time mismatch) was never a bug in `Sid`,
`AudioOutput`, `pygame`, or PyPy** (a *different*, real `pygame.mixer`
bug was still lurking underneath and surfaced once this one was fixed --
see the next addendum), confirmed two different ways before accepting
that conclusion: (1) a reference WAV
generated directly from `Sid.output_sample()`, completely bypassing
pygame, showed the exact same near-constant, never-fully-silent envelope
as the real recorded audio; (2) the measured ~190ms gap and the ~92/255
envelope level both match this project's own documented ADSR rate tables
to very close precision, confirming the envelope generator is behaving
exactly as designed, not misbehaving.

Fixed the actual cause: changed `release=8` to `release=1` (`POKE
54278,241` in `sound_test.bas`, matching change in
`sid_diagnostic.bas`'s per-voice ADSR setup) -- comfortably faster than
the ~190ms gap. Re-measured the same way: envelope now reaches **1 out
of 255** before each retrigger, i.e., genuinely silent, not a
lingering ~36%. Not yet re-confirmed by a second real Audacity capture
(that's the natural final verification step) but the underlying
mechanism is now fully understood and directly measured, not inferred.

Also found along the way, still open: `sid_diagnostic.bas` prints one
extra `VOICE`/waveform line (13 instead of the expected 12) somewhere in
its first few combinations -- fully reproducible, but *which* waveform
gets the extra print shifted (from `NOISE` to `PULSE`) after the
`release` fix, meaning it's timing-dependent rather than tied to a
specific waveform value. Not yet explained -- parked, since it doesn't
affect the audio content itself (register writes checked separately are
clean).

**Post-Phase-10 addendum: the `release` fix was real and necessary, but
not sufficient -- `pygame.mixer` itself turned out to have a genuine,
separate problem, fixed by switching to `sounddevice`.** Re-tested by
ear after the `release` fix: real playback still wasn't right --
"sounds like noise, no shape," then, at larger chunk sizes, "clean but
short with large gaps," then "each note splits into 4 pieces played
staccato." Ruled out, in order, with a real diagnostic for each: (1) a
raw `pygame`-only test (`scripts/pygame_tone_test.py`, independently
generated sine/triangle tones, single `.play()` call, no `AudioOutput`
involved) sounded "very clean, fantastic" -- rules out this machine's
pygame/SDL setup generally. (2) A reference WAV generated straight from
`Sid.output_sample()` and a capture of `AudioOutput`'s own produced
chunk *content*, both bypassing/exercising the real chunking path,
showed a perfectly continuous waveform -- no discontinuity at any chunk
boundary, ruling out a data bug. (3) `scripts/replay_sid_audio.py`
(pre-generate headlessly, replay *afterwards* through the same
small-chunk `play()`/`.queue()` mechanism, nothing else running)
sounded "very clean -- full scale, no jitter" -- rules out the chunked
delivery mechanism itself. (4) `--no-video-draw` (same real per-frame
loop, screen drawing skipped entirely, black screen) still produced the
same "4 pieces per note" -- rules out `pygame.display.flip()`/vsync
specifically. (5) A real, measured lookahead-buffer increase (not a
placebo -- `AudioOutput.buffered_seconds()` genuinely verified higher)
made it worse, not better ("lots more per note, closer together") --
rules out insufficient buffering margin as the mechanism, and this
project's own synthetic FPS benchmarks investigating *that* turned out
to be corrupted by real, fluctuating background system load in the
development environment (the same "50fps" baseline measurement
reproduced at "0.7fps" minutes later with zero code changes -- a
genuine confound, caught and disclosed rather than quietly trusted).
(6) At a moderate chunk size (200ms), the artifact clustered specifically
at the quiet, rapidly-decaying *end* of each note, never the loud
sustain -- consistent with some per-chunk effect in `pygame.mixer`
itself (a declick/resampling-filter reset applied per `Sound` object,
independent of the actual sample data already proven continuous) that a
loud sustain masks and a quiet release doesn't.

Every one of those rules out a data bug, a timing/buffering bug, and
video contention -- what's left, and the only remaining explanation
consistent with every single symptom above, is `pygame.mixer.Channel`
queueing discrete `Sound` objects being fundamentally unsuited to
continuously-synthesized audio like this, regardless of chunk size or
buffering. Fixed by replacing it entirely: `src/peripherals/audio.py`
now uses `sounddevice` (PortAudio bindings, `libportaudio2` on the
system) with a genuinely continuous, callback-driven stream -- `advance()`
appends samples to a plain `collections.deque`, and a background
PortAudio thread pulls directly from it whenever the real hardware wants
more data (padding with silence on underrun, not a click or a dropped
chunk). No discrete chunk objects, no `Channel.play()`/`.queue()`, no
chunk-size tuning at all. Verified directly against the real hardware
(this development environment has real ALSA/PipeWire devices, not just
`SDL_AUDIODRIVER=dummy`): `buffered_seconds()` self-regulates to a
small, stable ~60-70ms under real-time pacing, neither growing
unbounded nor draining to zero. `run_c64.py`'s lookahead-buffer loop and
`--audio-chunk-ms` flag, both built while chasing the wrong layer of
this problem, were removed as no longer meaningful; `--no-video-draw`
was kept since it's still a legitimate, reusable diagnostic. Not yet
re-confirmed by ear through the real fix (that's the actual, final
verification step) -- everything above is: no exceptions across the
full test suite (CPython and PyPy) and a real hardware smoke run, plus
the self-regulating buffer behavior, but not yet a human listening to
it.

**Post-Phase-10 addendum: `sounddevice` fixed the recurring per-note
artifact, but real playback still wasn't clean -- the final piece was a
genuine, quantified throughput deficit in `scripts/run_c64.py`'s own
combined loop, not anything in `Sid`/`AudioOutput`.** Re-tested by ear:
"first note is noise, gets less noisy... but all the notes are still
noisy." Every earlier diagnostic in this session's audio investigation
had been run *without* real screen rendering -- an unnoticed gap, caught
only when the user pointed out their own real-emulator experience (all
notes noisy) didn't match a capture that recovered after ~1.2s. Adding
the real `Screen.draw()`/`render_frame()` cost back into the same
diagnostic reproduced it exactly: `AudioOutput.buffered_seconds()`
stayed pinned near zero for 8+ real seconds straight, never climbing,
whenever the screen was drawn every frame -- not a one-time warm-up
window, a permanent structural deficit. Quantified directly, not
estimated: `machine.step()` for one frame's cycles costs ~12.3ms,
`render_frame()` ~3.7ms, `Screen.draw()` ~8.2ms -- **~24.2ms total
against a 19.95ms real-time budget**, over budget by itself before any
safety margin at all. Fixed by throttling actual screen drawing to
1-in-5 frames (`VIDEO_DRAW_EVERY_WITH_AUDIO` in `run_c64.py`) while
still stepping CPU/SID/audio every single frame -- verified this
produces a genuine, growing buffer margin (not just marginal
fluctuation) over an 8-second real-time-paced test, and that a full
real-usage capture (real `Screen`, throttled drawing, 12-16s, doubled
note lengths to rule out a coincidental timing match) shows clean,
correctly-structured notes throughout, with only a small residual
rough patch on the very first note (the interpreter's own JIT warm-up,
now a much smaller remaining factor than the throughput deficit that
was masking it). Real, explicit trade, not hidden: video refreshes at
~10Hz instead of ~50Hz while audio's on. Without audio (`--no-audio`),
this throughput problem doesn't exist and full-rate drawing is left
alone. User-confirmed on real hardware afterward: "a little crackling
on occasion, but I think we are good" -- the residual is understood
(JIT warm-up) and small, not the recurring, severe artifact from
earlier in this investigation.

**Post-Phase-10 addendum: reliable program input.** Raised before
starting Phase 11 -- the user noticed live keyboard input
(`peripherals/keyboard.py`) can be less than rock solid when typing a
BASIC program by hand, and wanted a quick way to load test programs
without waiting for real disk/cartridge support. Root cause identified,
not just patched around: `scripts/run_c64.py`'s main loop only drains
pygame's keyboard event queue once per simulated video frame, so a real
keypress fast enough that its down *and* up both land within one frame's
wall-clock duration (which can be tens of milliseconds on this project's
documented, unoptimized performance profile) nets out to a press the
emulated KERNAL never actually sees.

- [x] `src/peripherals/auto_type.py` — `AutoTyper`: types text reliably
      by holding each key for a fixed number of PHI2 cycles (decoupled
      from host speed or real typing speed) instead of relying on
      real-time keypress events -- the same technique this project's own
      validation scripts had already used by hand since Phase 9. Covers
      letters, digits, space, RETURN, and common punctuation, including
      shifted symbols (`"`, `(`, `)`, `!`, `&`, `'`, `<`, `>`, `?`)
      verified empirically the same way `KeyboardMatrix.KEY_POSITIONS`
      was, not guessed.
      **Measured too slow in practice on first landing, then actually
      fixed, not just excused**: the first version timed itself in
      *simulated video frames* (one `pump()` per iteration of
      `run_c64.py`'s main loop), which the user found measured at ~1
      character/second -- because every frame pays the full cost of
      CPU+chip emulation *and* screen rendering *and* audio generation
      *and* event polling (131ms/frame measured), not just the minimum
      the KERNAL's keyboard scan actually needs. Fixed two ways: (1)
      `advance(cycles)` replaces `pump()` (same shape as `CIA6526.tick`/
      `VicII.tick`), and `run_c64.py` now fast-forwards through typing --
      driving `Machine.step()` directly and skipping render/audio
      entirely while `AutoTyper.busy` (audio briefly off too, since SID
      ticking is the single most expensive part of a step); (2) the
      hold/gap durations themselves were re-measured (see the addendum
      below for why the *first* re-measurement, against the KERNAL's own
      `GETIN` called directly, was itself wrong). Combined result,
      measured on the real `sound_test.bas` (510 chars): **920ms/char →
      70.5ms/char (~13x)** -- the whole program now types in ~36s instead
      of an extrapolated ~8 minutes. Still not instant on this project's
      documented, unoptimized performance profile, but genuinely
      practical now, and -- unlike the first landing -- actually
      correct.
- [x] `scripts/run_c64.py --type-file program.bas` types a file in
      automatically once boot has settled at the READY prompt.
      Ctrl+V pastes the real system clipboard's text the same reliable
      way, at any point, via `pygame.scrap` (verified for real against a
      live X11 clipboard set with `xclip` on the machine this was
      developed on, not just headlessly).
- [x] `tests/peripherals/test_auto_type.py` — 9 tests. Caught a real bug
      before it shipped: `<`, `>`, and `?` were entirely missing from the
      character table, silently dropped (by design, for genuinely
      unmappable characters) rather than raising -- but for `<`/`>`
      specifically this corrupted real BASIC (`IF X<24` typed as
      `IF X24`), caught only by actually running the typed program
      through `Machine`, not by inspecting the mapping table.
- [x] `examples/sound_test.bas` and `examples/sprite_test.bas` -- small
      real BASIC programs (a scale on SID voice 1; a bouncing sprite)
      to test future chip/peripheral work against without needing disk
      support. Verified by actually typing and running both through the
      real `Machine` + `AutoTyper` pipeline: the sprite demo hit a real
      bug in the *program itself* (a 9-bit sprite X-coordinate poked
      directly as a 0-255 byte, correctly raising real BASIC's own
      `?ILLEGAL QUANTITY ERROR` once X exceeded 255 -- exactly what real
      hardware would do), fixed by keeping the demo's bounce range within
      a single byte rather than by changing anything in the emulator.
- [x] **Found from a real screenshot after the speedup landed, fixed the
      same day**: two more bugs, both real, both now fixed.
  1. **Sprites rendered on top of the border instead of behind it.**
      `src/c64/vic_ii.py`'s `_sprite_pixels()` clipped sprite pixels to
      the *full frame*, letting them paint over the border area. Checked
      against Christian Bauer's VIC-II article directly (not an AI
      summary of it -- a first WebSearch/WebFetch pass gave contradictory
      answers on two different framings of the same question; only
      reading the raw downloaded text of section 3.8.2 settled it):
      "Screen border" is the *highest*-priority element in both `MxDP`
      configurations, above every sprite -- real hardware clips sprites
      to the interior 320x200 display area by default. Fixed by clipping
      to that area instead of the full frame; see `docs/vic-ii.md`'s
      Sprites section. New regression test
      (`test_sprites_are_clipped_by_the_border_not_drawn_over_it`)
      verified to fail against the pre-fix code via `git stash` before
      trusting it.
  2. **Fast-forward typing loop silently discarded every non-QUIT event.**
      `scripts/run_c64.py`'s `AutoTyper.busy` fast-forward loop only
      checked `pygame.event.get()` for `QUIT`, throwing away everything
      else -- including KEYUP. A real Ctrl+V's Ctrl key-up landing
      mid-burst got discarded this way, leaving CTRL "stuck" pressed on
      the emulated matrix (via `peripherals/keyboard.py`'s normal
      live-forwarding path, which does map `K_LCTRL`/`K_RCTRL` to CTRL)
      for the rest of the burst -- turning every subsequent character
      `AutoTyper` typed into a `CTRL+<key>` combo. **This was a real,
      confirmed bug, genuinely worth fixing, but it turned out *not* to
      be what caused the garbled text in the second screenshot** -- see
      point 3 below, found only after the user reproduced the exact same
      garbling with plain `--type-file` (no Ctrl+V, no clipboard, no
      CTRL involved at all), which ruled this fix out as the explanation
      and pointed at something more fundamental. Still fixed here anyway
      since it's a real bug on its own, by extracting the event-handling
      logic (`_dispatch_events`) once and calling it identically from
      both the normal per-frame loop and the fast-forward loop's periodic
      UI check, instead of duplicating a shorter, lossier version for the
      latter. Verified directly: posting a `K_LCTRL` KEYDOWN then KEYUP
      through `_dispatch_events` now
      presses and then correctly releases CTRL on the matrix.
  3. **The real cause: `HOLD_CYCLES`/`GAP_CYCLES` were simply too short
      for the real KERNAL's interrupt-driven keyboard scan to reliably
      see every key.** The `8_000`/`20_000` pair shipped in the speedup
      above was "verified" against a harness that called `GETIN`
      directly -- which doesn't drive the real machine's interrupts, so
      it couldn't have caught this. Real hardware (and this emulator,
      correctly) scans the keyboard matrix and debounces once per jiffy
      IRQ, driven by CIA1 Timer A -- confirmed by reading back
      `$DC04`/`$DC05` after boot: a period of ~16,421 PHI2 cycles. A key
      held for less than one full period can land entirely between two
      scans and never be seen at all. Reproduced exactly, headlessly,
      with a script driving `Machine` + `AutoTyper` the same way
      `run_c64.py` does: typing `HELLO`+RETURN came back as `EO`. Swept
      real hold/gap values against that same booted-ROM harness (not the
      misleading `GETIN`-only one) until the *actual* real
      `examples/sprite_test.bas` file typed and `LIST`ed back with zero
      corruption: `HOLD_CYCLES = GAP_CYCLES = 20_000` (both comfortably
      above the ~16,421-cycle IRQ period; `16,421` itself was still
      marginal, `17,000` was clean). Slower than the broken numbers --
      **70.5ms/char, not 53.8ms/char** -- but correct, which the faster
      number never was. New regression tests in
      `tests/peripherals/test_auto_type_integration.py` boot the real
      staged ROMs and type real text through the actual interrupt-driven
      path, unlike `test_auto_type.py`'s `KeyboardMatrix`-in-isolation
      tests, which structurally cannot observe this class of bug.

## Phase 11 — Storage: disk + cartridge (cartridge done -- generic type only; disk not started)

- [x] **Cartridge (`.crt`) support, generic/type-0 hardware only.**
      Raised directly by the user wanting a `cartridge-slot/` directory
      to drop a real `.crt` file into and have it just work. Scoped
      explicitly before writing any code (matching this phase's own
      "decide fidelity level first" instinct below, applied to
      cartridges specifically): real `.crt` files can name 100+ distinct
      hardware types, most needing their own bespoke bank-switching
      register emulation (Action Replay, Ocean type, Fun Play, System 3,
      various freezer carts...) -- out of scope. Only hardware type 0
      (plain static ROM, no bank-switching registers at all) is
      supported; anything else raises `UnsupportedCartridge` with a
      specific reason, never a silent guess.
    - `src/c64/cartridge.py` -- `Cartridge.from_file` parses the real
      `.crt` container format (a structured header + CHIP packets, not
      a raw binary dump). Verified against the standard format
      reference *and* against a real, working 16K cartridge (a Galaxian
      conversion) parsed by hand before writing any code.
    - `src/c64/bus.py` extended with the real EXROM/GAME lines joining
      the *same* PLA logic that already gates BASIC/KERNAL ROM on
      LORAM/HIRAM -- not an independent override. The exact truth table
      was verified against VICE's own `c64meminit.c` source directly,
      not a summarized secondary source: a first web-search summary of
      a wiki table gave an internally self-contradictory answer for the
      one question that mattered (does ROML need LORAM, or does
      cartridge presence override the CPU port bits?) -- real emulator
      source settled it. The real, verified asymmetry: ROML needs EXROM
      active *and* LORAM *and* HIRAM; ROMH (16K mode only) needs only
      HIRAM, independent of LORAM. Confirmed with a real, unambiguous
      test (a distinctive non-zero RAM value written underneath, then
      toggling LORAM/HIRAM via real `$01` pokes through the DDR, not by
      poking the property directly) -- not just "it returned a
      plausible-looking number."
    - **Zero cartridge-specific code needed for autostart.** The real
      KERNAL's own boot routine checks for the "CBM80" signature and
      jumps to the cartridge's own reset vector -- since this project
      boots the genuine, unmodified KERNAL ROM, this happens
      automatically once ROML is mapped correctly. Verified directly:
      booting with the real Galaxian cartridge loaded, the genuine
      KERNAL jumped into the cartridge's own entry point ($8012,
      matching its own cold-reset vector exactly) within 33 CPU steps
      of reset.
    - `scripts/run_c64.py --cartridge path.crt` loads it explicitly;
      `cartridge-slot/` (gitignored, same convention as `roms/`) is just
      a suggested place to keep `.crt` files, never auto-scanned -- a
      plain run with no `--cartridge` flag stays cartridge-free even
      with files in that directory. Unsupported cartridges print a
      clear reason and the emulator continues without one, rather than
      crashing.
    - `docs/cartridge.md` -- the full format tables, the verified
      memory-map interaction, and known gaps, written before/alongside
      the code per this project's per-chip documentation convention.
    - `tests/c64/test_cartridge.py` (11 tests, synthetic `.crt` bytes
      built in-test -- no vendored cartridge images, matching this
      project's ROM-licensing discipline) and 6 new tests in
      `tests/c64/test_bus.py` covering the LORAM/HIRAM asymmetry and
      write-through-to-RAM behavior specifically.
    - **Real cartridges immediately exposed two genuine VIC-II gaps,
      both fixed, plus one substantial one deliberately not fixed yet.**
      The real Galaxian cartridge autostarted correctly but rendered a
      black screen: `$D011`/`$D016` showed BMM=1/MCM=1 (multicolor
      bitmap mode), stored but entirely inert until now. Added bitmap
      mode (both hi-res and multicolor sub-modes) to `VicII`/
      `render_frame` -- see docs/vic-ii.md for the full, verified
      register/memory-layout details. Verified against the real
      cartridge, not just synthetic tests: `scripts/render_frame.py
      --cartridge` now produces the exact, legible real Galaxian title
      screen ("ATARISOFT PRESENTS... GALAXIAN...", correct colors).
      A second real cartridge (Frogger) then exposed a *different* gap
      the same way: its gameplay screen also rendered black, this time
      because it uses **multicolor text mode** (MCM=1, BMM=0), also
      entirely unimplemented -- added, including the real, per-cell
      hardware behavior (each cell's own color RAM bit 3 decides
      hi-res-vs-multicolor for that cell, not a single global switch).
      Verified the same way: Frogger's real gameplay screen (traffic,
      river, "FAST"/"R=04" HUD) rendered fully legible. Along the way,
      `scripts/render_frame.py` itself turned out to have a real bug --
      it drove a raw `CPU`+`Bus` with no interrupt delivery at all,
      silently leaving Frogger's actual (IRQ-driven) screen-drawing code
      never running; fixed by having it use `Machine` instead.
      **A third, deeper limitation surfaced from the same Frogger
      cartridge, deliberately left unfixed**: it changes `$D018`
      (character set select) to two different values at two different
      raster lines within a single frame (confirmed directly, not
      guessed -- `0x14`/`0x12` at raster 252, `0x14` at raster 161), a
      real, deliberate raster-split technique giving its river and road
      sections different graphics. `render_frame()`'s one-shot,
      whole-frame-snapshot design can't represent that -- whichever
      register value happens to be current at the moment it's called,
      one half of the screen renders wrong. This is the same
      already-documented "not cycle-accurate, nothing interleaves CPU
      and VIC-II per-scanline" gap, now confirmed against real software
      rather than theoretical -- fixing it means `render_frame()`
      becoming a genuinely incremental, per-scanline renderer, a
      substantial architecture change explicitly deferred, not
      attempted this session. (Checked the cartridge file's own MD5
      hash first, to rule out a corrupted dump before concluding this
      was a rendering gap rather than a bad file.)
- [ ] Decide fidelity level explicitly before starting disk: a real
      1541 emulation is itself another whole 6502+ROM+RAM machine
      talking a serial protocol (would reuse `c6502` a second time) —
      much bigger than a "fake fast-load" that intercepts KERNAL's LOAD
      routine and feeds bytes straight from a `.d64` file, which is what
      most simplified emulators actually do. Possibly split into both,
      in that order.
- [ ] Blank/writable disk image creation, so software running in the
      emulator can actually save data back out to a real file (raised
      alongside the original `peripherals/` idea).
