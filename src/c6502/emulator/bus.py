"""Flat memory for CPU-in-isolation testing.

Ported from c-compiler-6502's Phase 1 (see CLAUDE.md): FlatMemory (a flat
64KB RAM) is what the CPU core's own tests run against, and what Klaus
Dormann's functional test suite wants too -- it just needs contiguous
writable RAM at a configurable address, not a real memory map.

The *real* C64 memory map (RAM/ROM/color-RAM/bank-switching via the 6510's
$00/$01 I/O port, VIC-II/SID/CIA register windows) is Phase 2 of this
project's own roadmap (docs/roadmap.md) -- deliberately not started yet,
and won't live in this file (a real Bus belongs in src/c64/ once built,
not bolted onto this ported module).
"""

from __future__ import annotations


class FlatMemory:
    """A flat block of RAM implementing the CPU's read8/write8 interface."""

    def __init__(self, size: int = 0x10000) -> None:
        self._data = bytearray(size)

    def read8(self, address: int) -> int:
        return self._data[address & 0xFFFF]

    def write8(self, address: int, value: int) -> None:
        self._data[address & 0xFFFF] = value & 0xFF

    def read16(self, address: int) -> int:
        lo = self.read8(address)
        hi = self.read8((address + 1) & 0xFFFF)
        return lo | (hi << 8)

    def write16(self, address: int, value: int) -> None:
        self.write8(address, value & 0xFF)
        self.write8((address + 1) & 0xFFFF, (value >> 8) & 0xFF)

    def load(self, address: int, data: bytes) -> None:
        for offset, byte in enumerate(data):
            self.write8(address + offset, byte)
