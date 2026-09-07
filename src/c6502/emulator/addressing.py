"""Addressing-mode resolution for the NMOS 6502.

Each function consumes whatever operand bytes its mode needs (advancing
cpu.pc via cpu.fetch_u8()/fetch_u16()) and returns (address, page_crossed):
  - address is None for implied/accumulator (the instruction operates on a
    register directly, not memory).
  - For every other mode, address is a memory location -- including
    immediate mode, where it's the address of the operand byte itself
    (i.e. the old PC), so instruction code can always do
    `cpu.bus.read8(address)` uniformly regardless of mode.
  - page_crossed is only meaningful for the indexed modes where hardware
    charges an extra cycle for it (see opcodes.py's extra_on_page_cross).

JMP (indirect)'s page-wrap bug is reproduced deliberately here -- see
docs/6502-reference.md.
"""

from __future__ import annotations

from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .cpu import CPU

AddressResult = Tuple[Optional[int], bool]


def implied(cpu: "CPU") -> AddressResult:
    return None, False


# Accumulator mode has the same "no memory operand" shape as implied;
# instructions that support it (ASL/LSR/ROL/ROR) check for address is None
# and operate on cpu.a instead.
accumulator = implied


def immediate(cpu: "CPU") -> AddressResult:
    address = cpu.pc
    cpu.pc = (cpu.pc + 1) & 0xFFFF
    return address, False


def zero_page(cpu: "CPU") -> AddressResult:
    return cpu.fetch_u8(), False


def zero_page_x(cpu: "CPU") -> AddressResult:
    base = cpu.fetch_u8()
    return (base + cpu.x) & 0xFF, False


def zero_page_y(cpu: "CPU") -> AddressResult:
    base = cpu.fetch_u8()
    return (base + cpu.y) & 0xFF, False


def absolute(cpu: "CPU") -> AddressResult:
    return cpu.fetch_u16(), False


def absolute_x(cpu: "CPU") -> AddressResult:
    base = cpu.fetch_u16()
    address = (base + cpu.x) & 0xFFFF
    return address, (base & 0xFF00) != (address & 0xFF00)


def absolute_y(cpu: "CPU") -> AddressResult:
    base = cpu.fetch_u16()
    address = (base + cpu.y) & 0xFFFF
    return address, (base & 0xFF00) != (address & 0xFF00)


def indirect(cpu: "CPU") -> AddressResult:
    pointer = cpu.fetch_u16()
    lo = cpu.bus.read8(pointer)
    if pointer & 0xFF == 0xFF:
        # NMOS bug: the high byte wraps within the same page instead of
        # crossing into the next one. Reproduced deliberately, not fixed.
        hi = cpu.bus.read8(pointer & 0xFF00)
    else:
        hi = cpu.bus.read8(pointer + 1)
    return lo | (hi << 8), False


def indexed_indirect(cpu: "CPU") -> AddressResult:
    """(zp,X): add X (with zero-page wraparound) before dereferencing."""
    base = cpu.fetch_u8()
    pointer = (base + cpu.x) & 0xFF
    lo = cpu.bus.read8(pointer)
    hi = cpu.bus.read8((pointer + 1) & 0xFF)
    return lo | (hi << 8), False


def indirect_indexed(cpu: "CPU") -> AddressResult:
    """(zp),Y: dereference first, then add Y to the resulting address."""
    base = cpu.fetch_u8()
    lo = cpu.bus.read8(base)
    hi = cpu.bus.read8((base + 1) & 0xFF)
    pointer = lo | (hi << 8)
    address = (pointer + cpu.y) & 0xFFFF
    return address, (pointer & 0xFF00) != (address & 0xFF00)


def relative(cpu: "CPU") -> AddressResult:
    """Branches: signed 8-bit offset from the PC just past this instruction."""
    offset = cpu.fetch_u8()
    if offset >= 0x80:
        offset -= 0x100
    target = (cpu.pc + offset) & 0xFFFF
    return target, False
