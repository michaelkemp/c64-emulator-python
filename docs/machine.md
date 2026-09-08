# The real machine: closing the loop

Every chip so far (`Bus`, `CIA6526`×2, `VicII`, `Sid`) has a `tick(cycles)`
or equivalent interface, but nothing before this actually called them
together from real CPU execution, and nothing delivered a chip's
interrupt output to the CPU's actual IRQ/NMI pins -- every phase doc
(`docs/cia.md`, `docs/vic-ii.md`, `docs/sid.md`) flagged this as the same
outstanding gap. `src/c64/machine.py`'s `Machine` class is that missing
piece: it owns one of each chip, plus the keyboard matrix and joysticks,
and its `step()` method is the real system clock.

## What `step()` does, in order

1. `cpu.step()` executes exactly one instruction and reports how many
   PHI2 cycles it actually took (`StepResult.cycles` -- already exact,
   from the ported CPU core, per instruction and addressing mode).
2. That exact cycle count is fed to `cia1.tick()`, `cia2.tick()`,
   `vic.tick()`, and `sid.tick()` -- so every chip advances by exactly as
   much real time as the CPU just spent, not an approximation.
3. Interrupts are checked *after* the instruction completes (matching how
   a real 6502 samples its interrupt lines between instructions, and how
   every non-cycle-stepped 6502 emulator approximates it):
   - **IRQ is level-triggered**: `cia1.irq_line or vic.irq_line` is
     checked every step, and `cpu.irq()` is called whenever either is
     true. This is safe to call even when nothing new happened -- the
     ported CPU core's own `irq()` already no-ops when the I flag is set,
     exactly matching real hardware's level-sensitive IRQ pin (a
     software interrupt handler is expected to clear its source's flag
     before returning, which drops the line and stops repeat delivery).
   - **NMI is edge-triggered**: `cia2.irq_line`'s *rising* edge (not its
     level) triggers `cpu.nmi()` -- called once per 0->1 transition, not
     once per step while held, matching real 6502 NMI semantics (a real
     NMI pin held low only interrupts once; re-arming requires the line
     to go high again first).

## Known gaps (carried over, now partially addressed)

- **Still not cycle-exact within an instruction.** Interrupts are
  recognized once per completed instruction, not at the precise cycle a
  real 6502 would sample its interrupt pins mid-instruction. This is the
  standard approximation essentially every non-cycle-stepped 6502
  emulator makes, and is a real (if usually small) source of divergence
  from cycle-perfect timing-sensitive real software.
- **Badlines still don't steal cycles.** `VicII.is_badline` is now being
  evaluated against real elapsed cycles (via `vic.tick()`), but `step()`
  doesn't yet reduce the CPU's own cycle budget on a bad line -- that
  would require knowing badline status *before* running the next
  instruction and stalling the CPU core itself, a deeper change than
  this phase makes.
- **Nothing paces real time yet.** `Machine.step()` runs as fast as
  Python allows -- there's no wall-clock throttling. That's fine for
  screen output (Phase 8) but audio (Phase 10) will need it, since audio
  pitch is wrong if cycles aren't spent at the real PAL rate.

## Performance: real-time is genuinely not reached yet, and that's expected

Measured on the machine this was developed on, running the real
KERNAL+BASIC (`scripts/run_c64.py`'s actual workload): one simulated PAL
frame (`CYCLES_PER_FRAME` = 19,656 PHI2 cycles) took **85.7ms** with
`enable_audio=True` (~11.7fps achievable) and **29.7ms** with it `False`
(~33.7fps achievable) -- against a 20ms/50fps real-hardware target.

Profiling (`cProfile`, 10 frames, `enable_audio=True`) showed `Sid.tick`
alone accounting for over half of total time (1.265s of 2.305s) -- by far
the most expensive of the four chips being ticked every cycle, and pure
waste whenever nothing consumes its audio output. `Machine`'s
`enable_audio` flag (default `False`) skips it entirely until Phase 10
needs it, which is most of the gap above. What's left (29.7ms, still
short of 20ms) is genuine CPU+CIA+VIC-II emulation cost, not identified
waste -- this project made no deliberate speed-optimization pass beyond
that one fix through Phases 0-8, correctness having been the priority.

**A real speed effort turned out to be worth doing, and PyPy is it.**
Raised once real playback of `examples/sound_test.bas` came out as short
stuttering ticks instead of a steady note -- a direct, audible
consequence of `enable_audio=True` running well under real-time (see
above): `pygame.mixer` runs dry between generated chunks and re-triggers
playback from silence each time, correct pitch but no continuity. Tried
PyPy instead of guessing at micro-optimizations first, since it costs
nothing to test (same Python source, no code changes) and this is
exactly the kind of tight, hot, pure-Python-bytecode loop its JIT
targets well. Measured on this project's own real workloads, same
machine, back-to-back against CPython:

| Benchmark | CPython | PyPy | Speedup |
|---|---|---|---|
| Core loop, `enable_audio=False` | 740,160 Hz (75% of real PAL) | 4,943,701 Hz (**502%** of real PAL) | 6.7x |
| Core loop, `enable_audio=True` | 268,935 Hz (27% of real PAL) | 2,054,321 Hz (**208%** of real PAL) | 7.6x |
| Dormann 30.6M-step CPU suite | 74.0s | 8.4s | 8.8x |
| Real ROM boot + AutoTyper (full integration test) | 36.0s | 7.3s | 4.9x |

Every test in the suite -- including the ones needing `pygame`, which
has a prebuilt PyPy wheel, no compilation required -- passes identically
under PyPy; the Dormann suite in particular is a strong correctness
signal since it's a bit-for-bit CPU core validation, not just a speed
benchmark. With audio on, PyPy runs at **2.08x real-time** instead of
CPython's 3.66x *slower* -- comfortably outpacing playback consumption
instead of falling behind it, which should eliminate the stuttering
outright (not yet re-confirmed by ear through real `pygame.mixer`
output, only measured at the `Machine`-loop level).

**Update**: `pygame.mixer` itself turned out to have a real, separate bug
(discrete `Sound`-object queueing isn't suited to continuously-synthesized
audio, regardless of chunk size or buffering) -- replaced with
`sounddevice`'s continuous, callback-driven streaming. See
`peripherals/audio.py`'s module docstring and `docs/roadmap.md`'s
post-Phase-10 addenda for the full diagnostic chain.

One real caveat, not glossed over: the `pypy3` package available via
`apt` at the time of this measurement only targets Python **3.9**
language level. `requires-python` was lowered from `3.11` to `3.9`
specifically to make this a supported combination (verified first that
nothing in this codebase actually uses 3.10+-only syntax -- no
`match`/`case`, `except*`, `tomllib`, or `typing.Self`). A newer PyPy
build with 3.10/3.11 support exists upstream but isn't in `apt` on this
machine; revisit if this project ever needs newer language features.
**Recommended**: use PyPy for any audio-enabled run, or generally once
available -- `pip install pypy3` isn't a thing; get it via your system
package manager (`apt install pypy3` on Debian/Ubuntu) or
[pypy.org](https://www.pypy.org/download.html), then `pypy3 -m venv` +
`pip install -e ".[dev,peripherals]"` the same as CPython.

## Verified

A real integration check (see `docs/roadmap.md`'s Phase 7): booting the
genuine, unmodified KERNAL+BASIC through `Machine` for several million
instructions shows the KERNAL's own jiffy-clock counter (`$A0`-`$A2`,
the real, documented 3-byte "TIME" counter every C64 KERNAL maintains)
actually incrementing -- concrete proof that CIA1's Timer A underflow is
reaching `irq_line`, `Machine.step()` is delivering it to the CPU, the
real KERNAL's IRQ handler is running and doing its real job, and
execution correctly resumes afterward. Nothing about that behavior was
hand-tuned; it's what the genuine ROM code does when the interrupt
plumbing actually works.
