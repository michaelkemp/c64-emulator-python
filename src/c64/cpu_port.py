"""The 6510's zero-page I/O port: $00 (data direction) / $01 (data).

The C64's CPU is a 6510, not a plain 6502: same core, plus a small 6-bit
I/O port built into the chip and addressed at $00/$01. Three of those
bits -- LORAM, HIRAM, CHAREN -- are what the C64 uses to bank ROM, RAM,
and I/O in and out of the address space; `Bus` (bus.py) reads them to
decide what's visible where. The rest of the port drives the datasette
(motor, sense, write) and isn't emulated here yet -- nothing in this
project needs it so far.

This lives as its own small memory-mapped device, not a change to the
ported 6502 core in `src/c6502/` -- see CLAUDE.md's "Key decisions
carried over as guidance" section for why that split is deliberate.

Known simplification: on real hardware, a port line configured as input
(its DDR bit clear) floats to whatever it was last driven to and slowly
decays towards 1 (weak pull-ups, plus a well-documented "fading bits"
capacitive effect a handful of demos exploit). Here, an input bit just
reads as 1 unconditionally -- this is what makes ROM visible at reset
before the KERNAL has written anything to $01 (LORAM/HIRAM/CHAREN all
default "on"), which is the only behavior anything in this project
currently depends on.
"""

from __future__ import annotations

LORAM_BIT = 0x01
HIRAM_BIT = 0x02
CHAREN_BIT = 0x04


class CpuPort:
    """The 6510's $00 (DDR) / $01 (data) registers."""

    def __init__(self) -> None:
        self.ddr = 0x00
        self._latch = 0x00

    def read_ddr(self) -> int:
        return self.ddr

    def write_ddr(self, value: int) -> None:
        self.ddr = value & 0xFF

    def read_data(self) -> int:
        driven = self._latch & self.ddr
        floating = ~self.ddr & 0xFF  # undriven bits read as 1
        return driven | floating

    def write_data(self, value: int) -> None:
        self._latch = value & 0xFF

    @property
    def loram(self) -> bool:
        return bool(self.read_data() & LORAM_BIT)

    @property
    def hiram(self) -> bool:
        return bool(self.read_data() & HIRAM_BIT)

    @property
    def charen(self) -> bool:
        return bool(self.read_data() & CHAREN_BIT)
