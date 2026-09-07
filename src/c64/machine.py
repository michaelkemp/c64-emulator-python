"""The real C64: CPU + Bus + both CIAs + VIC-II + SID, driven together
cycle-by-cycle with real interrupt delivery.

See docs/machine.md for exactly what `step()` does and in what order,
why IRQ is level-triggered but NMI is edge-triggered, and this phase's
known gaps (still not cycle-exact within an instruction, badlines still
don't steal cycles, nothing paces real wall-clock time yet).

`enable_audio` (default off): SID's per-cycle oscillator/envelope work is
by far the most expensive of the four chips being ticked every step (see
docs/machine.md's profiling numbers) -- pure waste while nothing consumes
its audio output (Phase 8/9 don't). Leave it off for screen-only/
keyboard use; Phase 10 will need it on for real audio. Software that
polls `$D41B`/`$D41C` (OSC3/ENV3) as a hardware random-number source
*without* making sound also needs it on, or those registers just freeze.
"""

from __future__ import annotations

from pathlib import Path

from c6502.emulator.cpu import CPU

from c64.bus import Bus
from c64.cia import CIA6526
from c64.joystick import Joystick
from c64.keyboard_matrix import Cia1Ports, KeyboardMatrix
from c64.sid import Sid
from c64.vic_ii import VicII


class Machine:
    def __init__(
        self,
        *,
        basic_rom: bytes | None = None,
        kernal_rom: bytes | None = None,
        char_rom: bytes | None = None,
        sample_rate: int = 44100,
        enable_audio: bool = False,
    ) -> None:
        self.keyboard = KeyboardMatrix()
        self.joystick1 = Joystick()
        self.joystick2 = Joystick()
        self.cia1 = CIA6526(
            port_coupler=Cia1Ports(self.keyboard, joystick_port1=self.joystick1, joystick_port2=self.joystick2)
        )
        self.cia2 = CIA6526()
        self.vic = VicII()
        self.sid = Sid(sample_rate=sample_rate)
        self.bus = Bus(
            basic_rom=basic_rom,
            kernal_rom=kernal_rom,
            char_rom=char_rom,
            vic=self.vic,
            sid=self.sid,
            cia1=self.cia1,
            cia2=self.cia2,
        )
        self.cpu = CPU(self.bus)
        self.cpu.reset()
        self._prev_nmi_line = False
        self.enable_audio = enable_audio

    @classmethod
    def from_roms(cls, roms_dir: Path | str = "roms/c64", **kwargs) -> "Machine":
        roms_dir = Path(roms_dir)
        roms = {}
        for name, key in (("kernal", "kernal_rom"), ("basic", "basic_rom"), ("chargen", "char_rom")):
            path = roms_dir / name
            if path.exists():
                roms[key] = path.read_bytes()
        return cls(**roms, **kwargs)

    def step(self) -> int:
        """Execute exactly one CPU instruction, advance every chip by the
        same real elapsed cycles, and deliver any pending interrupts.
        Returns the number of PHI2 cycles this step consumed."""
        result = self.cpu.step()
        cycles = result.cycles

        self.cia1.tick(cycles)
        self.cia2.tick(cycles)
        self.vic.tick(cycles)
        if self.enable_audio:
            self.sid.tick(cycles)

        if self.cia1.irq_line or self.vic.irq_line:
            self.cpu.irq()

        nmi_line = self.cia2.irq_line
        if nmi_line and not self._prev_nmi_line:
            self.cpu.nmi()
        self._prev_nmi_line = nmi_line

        return cycles

    def run(self, instructions: int) -> int:
        """Run exactly `instructions` steps, returning total cycles spent."""
        total = 0
        for _ in range(instructions):
            total += self.step()
        return total
