"""CPU core for the NMOS 6502.

Registers, flags, the fetch/decode/execute step() loop, reset, and basic
interrupt handling. See docs/6502-reference.md for the ISA notes this is
built against, docs/testing-strategy.md for how it's validated, and
docs/roadmap.md for what's implemented vs deferred. Most undocumented/
"illegal" opcodes are implemented (see opcodes.py); the remaining
chip-unstable ones fall through to IllegalOpcodeError below, and the 12
JAM/KIL opcodes raise the distinct ProcessorJammed instead (see both for
why they're modeled differently).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .opcodes import OPCODES
from .vectors import IRQ_VECTOR, NMI_VECTOR, RESET_VECTOR


class Memory(Protocol):
    def read8(self, address: int) -> int: ...
    def write8(self, address: int, value: int) -> None: ...


class IllegalOpcodeError(Exception):
    """Raised for any opcode byte not in opcodes.OPCODES.

    Most undocumented/"illegal" 6502 opcodes are implemented (see
    opcodes.py); the ones still deliberately unimplemented are the
    chip-unstable group whose real behavior varies by chip series/analog
    bus conditions (ANE/XAA, LXA, LAS, SHA, SHX, SHY, TAS) -- see
    docs/6502-reference.md. This stays a loud failure rather than a
    silent NOP so a program that depends on one of those is obvious, not
    subtly wrong.
    """

    def __init__(self, opcode: int, pc: int) -> None:
        super().__init__(f"illegal/unimplemented opcode ${opcode:02X} at ${pc:04X}")
        self.opcode = opcode
        self.pc = pc


class ProcessorJammed(Exception):
    """Raised when a JAM/KIL/HLT opcode executes (12 opcode values -- see
    opcodes.py's illegal-opcode section).

    On real NMOS 6502/6510 hardware these genuinely freeze the CPU in an
    internal fetch cycle -- there is no defined "next instruction", only a
    hardware reset gets it out. Kept as its own exception rather than
    folded into IllegalOpcodeError: this *is* real, documented opcode
    behavior, not something unimplemented -- a caller may reasonably want
    to catch this specifically (e.g. to model a reset) rather than treat
    it the same as an unimplemented opcode.
    """

    def __init__(self, opcode: int, pc: int) -> None:
        super().__init__(f"JAM/KIL opcode ${opcode:02X} at ${pc:04X} -- CPU halted, needs reset")
        self.opcode = opcode
        self.pc = pc


class Flags:
    """The 6502 status register (P), stored as individual named flags.

    Bit 5 ("unused") and the "B flag" (bit 4) are not real, persistently
    stored bits on real hardware -- they only appear in the byte produced
    when P is pushed to the stack (bit 5 always set, bit 4 set only for a
    PHP/BRK push, clear for a hardware IRQ/NMI push). See
    docs/6502-reference.md.
    """

    def __init__(self) -> None:
        self.n = False
        self.v = False
        self.d = False
        self.i = False
        self.z = False
        self.c = False

    def pack(self, brk: bool) -> int:
        value = 0x20  # bit 5 always reads back as 1
        if self.n:
            value |= 0x80
        if self.v:
            value |= 0x40
        if brk:
            value |= 0x10
        if self.d:
            value |= 0x08
        if self.i:
            value |= 0x04
        if self.z:
            value |= 0x02
        if self.c:
            value |= 0x01
        return value

    def unpack(self, byte: int) -> None:
        self.n = bool(byte & 0x80)
        self.v = bool(byte & 0x40)
        self.d = bool(byte & 0x08)
        self.i = bool(byte & 0x04)
        self.z = bool(byte & 0x02)
        self.c = bool(byte & 0x01)


@dataclass
class StepResult:
    """Everything trace.py needs to print one line for an executed instruction."""

    pc: int
    opcode: int
    mnemonic: str
    mode: str
    operand_bytes: bytes
    cycles: int
    a: int
    x: int
    y: int
    sp: int
    p: int


class CPU:
    def __init__(self, bus: Memory) -> None:
        self.bus = bus
        self.a = 0
        self.x = 0
        self.y = 0
        self.sp = 0xFD
        self.pc = 0
        self.flags = Flags()

    def reset(self) -> None:
        # Real hardware leaves A/X/Y and most flags at whatever they held
        # before reset -- an emulator has to pick something at power-on, so
        # this is a deliberate convention (zero/clear), not a hardware claim.
        self.a = 0
        self.x = 0
        self.y = 0
        self.sp = 0xFD
        self.flags = Flags()
        self.flags.i = True
        self.pc = self._read16(RESET_VECTOR)

    def _read16(self, address: int) -> int:
        lo = self.bus.read8(address)
        hi = self.bus.read8((address + 1) & 0xFFFF)
        return lo | (hi << 8)

    def fetch_u8(self) -> int:
        value = self.bus.read8(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return value

    def fetch_u16(self) -> int:
        lo = self.fetch_u8()
        hi = self.fetch_u8()
        return lo | (hi << 8)

    def push8(self, value: int) -> None:
        self.bus.write8(0x0100 + self.sp, value & 0xFF)
        self.sp = (self.sp - 1) & 0xFF

    def pull8(self) -> int:
        self.sp = (self.sp + 1) & 0xFF
        return self.bus.read8(0x0100 + self.sp)

    def push16(self, value: int) -> None:
        self.push8((value >> 8) & 0xFF)
        self.push8(value & 0xFF)

    def pull16(self) -> int:
        lo = self.pull8()
        hi = self.pull8()
        return lo | (hi << 8)

    def set_zn(self, value: int) -> None:
        value &= 0xFF
        self.flags.z = value == 0
        self.flags.n = bool(value & 0x80)

    def step(self) -> StepResult:
        pc_start = self.pc
        opcode = self.fetch_u8()
        spec = OPCODES.get(opcode)
        if spec is None:
            raise IllegalOpcodeError(opcode, pc_start)

        operand_start = self.pc
        address, page_crossed = spec.addressing_fn(self)
        operand_bytes = bytes(
            self.bus.read8(addr & 0xFFFF) for addr in range(operand_start, self.pc)
        )

        extra = spec.instruction_fn(self, address) or 0
        cycles = spec.base_cycles + extra
        if spec.extra_on_page_cross and page_crossed:
            cycles += 1

        return StepResult(
            pc=pc_start,
            opcode=opcode,
            mnemonic=spec.mnemonic,
            mode=spec.mode,
            operand_bytes=operand_bytes,
            cycles=cycles,
            a=self.a,
            x=self.x,
            y=self.y,
            sp=self.sp,
            p=self.flags.pack(brk=False),
        )

    def irq(self) -> None:
        if self.flags.i:
            return
        self.push16(self.pc)
        self.push8(self.flags.pack(brk=False))
        self.flags.i = True
        self.pc = self._read16(IRQ_VECTOR)

    def nmi(self) -> None:
        self.push16(self.pc)
        self.push8(self.flags.pack(brk=False))
        self.flags.i = True
        self.pc = self._read16(NMI_VECTOR)
