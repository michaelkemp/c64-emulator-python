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
