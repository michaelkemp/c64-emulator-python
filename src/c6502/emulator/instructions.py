"""Instruction semantics for the NMOS 6502, one function per mnemonic.

Every function has the shape `(cpu, address) -> int`, where `address` is
whatever addressing.py resolved (None for implied/accumulator) and the
return value is any *extra* cycles beyond the opcode's base count (branch
taken/page-crossed, etc.) -- see opcodes.py and cpu.py's step().

Grouped by family, matching tests/emulator/test_*.py.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .vectors import IRQ_VECTOR

if TYPE_CHECKING:
    from .cpu import CPU


# --- loads / stores ---------------------------------------------------

def lda(cpu: "CPU", address: int) -> int:
    cpu.a = cpu.bus.read8(address)
    cpu.set_zn(cpu.a)
    return 0


def ldx(cpu: "CPU", address: int) -> int:
    cpu.x = cpu.bus.read8(address)
    cpu.set_zn(cpu.x)
    return 0


def ldy(cpu: "CPU", address: int) -> int:
    cpu.y = cpu.bus.read8(address)
    cpu.set_zn(cpu.y)
    return 0


def sta(cpu: "CPU", address: int) -> int:
    cpu.bus.write8(address, cpu.a)
    return 0


def stx(cpu: "CPU", address: int) -> int:
    cpu.bus.write8(address, cpu.x)
    return 0


def sty(cpu: "CPU", address: int) -> int:
    cpu.bus.write8(address, cpu.y)
    return 0


# --- transfers / stack --------------------------------------------------

def tax(cpu: "CPU", address: Optional[int]) -> int:
    cpu.x = cpu.a
    cpu.set_zn(cpu.x)
    return 0


def tay(cpu: "CPU", address: Optional[int]) -> int:
    cpu.y = cpu.a
    cpu.set_zn(cpu.y)
    return 0


def txa(cpu: "CPU", address: Optional[int]) -> int:
    cpu.a = cpu.x
    cpu.set_zn(cpu.a)
    return 0


def tya(cpu: "CPU", address: Optional[int]) -> int:
    cpu.a = cpu.y
    cpu.set_zn(cpu.a)
    return 0


def tsx(cpu: "CPU", address: Optional[int]) -> int:
    cpu.x = cpu.sp
    cpu.set_zn(cpu.x)
    return 0


def txs(cpu: "CPU", address: Optional[int]) -> int:
    cpu.sp = cpu.x  # deliberately does not touch flags
    return 0


def pha(cpu: "CPU", address: Optional[int]) -> int:
    cpu.push8(cpu.a)
    return 0


def pla(cpu: "CPU", address: Optional[int]) -> int:
    cpu.a = cpu.pull8()
    cpu.set_zn(cpu.a)
    return 0


def php(cpu: "CPU", address: Optional[int]) -> int:
    cpu.push8(cpu.flags.pack(brk=True))
    return 0


def plp(cpu: "CPU", address: Optional[int]) -> int:
    cpu.flags.unpack(cpu.pull8())
    return 0


# --- logic ---------------------------------------------------------------

def and_(cpu: "CPU", address: int) -> int:
    cpu.a &= cpu.bus.read8(address)
    cpu.set_zn(cpu.a)
    return 0


def ora(cpu: "CPU", address: int) -> int:
    cpu.a |= cpu.bus.read8(address)
    cpu.set_zn(cpu.a)
    return 0


def eor(cpu: "CPU", address: int) -> int:
    cpu.a ^= cpu.bus.read8(address)
    cpu.set_zn(cpu.a)
    return 0


def bit(cpu: "CPU", address: int) -> int:
    value = cpu.bus.read8(address)
    cpu.flags.z = (cpu.a & value) == 0
    cpu.flags.n = bool(value & 0x80)
    cpu.flags.v = bool(value & 0x40)
    return 0


# --- arithmetic ------------------------------------------------------------

def _adc_binary(cpu: "CPU", value: int) -> int:
    carry_in = 1 if cpu.flags.c else 0
    total = cpu.a + value + carry_in
    result = total & 0xFF
    cpu.flags.c = total > 0xFF
    cpu.flags.v = bool((~(cpu.a ^ value) & (cpu.a ^ result)) & 0x80)
    cpu.set_zn(result)
    return result


def _adc_decimal(cpu: "CPU", value: int) -> int:
    # NMOS decimal-mode flag behavior is notoriously quirky; this follows
    # the commonly documented algorithm (per-nibble BCD correction, N/V
    # from the result before high-nibble correction, Z from the binary
    # sum). Treat as best-effort -- final correctness is validated against
    # Klaus Dormann's dedicated decimal test in Phase 3, not asserted here.
    carry_in = 1 if cpu.flags.c else 0
    a = cpu.a
    lo = (a & 0x0F) + (value & 0x0F) + carry_in
    if lo > 9:
        lo = (lo + 6) & 0x0F
        hi_carry = 1
    else:
        hi_carry = 0
    hi = (a >> 4) + (value >> 4) + hi_carry

    pre_correction = ((hi & 0x0F) << 4) | lo
    cpu.flags.n = bool(pre_correction & 0x80)
    cpu.flags.v = bool((~(a ^ value) & (a ^ pre_correction)) & 0x80)

    if hi > 9:
        hi += 6
    cpu.flags.c = hi > 15

    binary_result = (a + value + carry_in) & 0xFF
    cpu.flags.z = binary_result == 0

    return ((hi & 0x0F) << 4) | lo


def _apply_adc(cpu: "CPU", value: int) -> None:
    if cpu.flags.d:
        result = _adc_decimal(cpu, value)
    else:
        result = _adc_binary(cpu, value)
    cpu.a = result & 0xFF


def adc(cpu: "CPU", address: int) -> int:
    _apply_adc(cpu, cpu.bus.read8(address))
    return 0


def _sbc_decimal(cpu: "CPU", value: int) -> int:
    # See _adc_decimal's note -- same caveat applies here.
    carry_in = 1 if cpu.flags.c else 0
    a = cpu.a
    # Binary subtraction (via ones-complement ADC) drives N/V/Z; the
    # decimal correction below only overrides C with the correct BCD
    # borrow/carry.
    _adc_binary(cpu, (~value) & 0xFF)

    lo = (a & 0x0F) - (value & 0x0F) - (1 - carry_in)
    hi = (a >> 4) - (value >> 4)
    if lo < 0:
        lo = (lo - 6) & 0x0F
        hi -= 1
    if hi < 0:
        hi = (hi - 6) & 0x0F
        cpu.flags.c = False
    else:
        cpu.flags.c = True

    return ((hi & 0x0F) << 4) | (lo & 0x0F)


def _apply_sbc(cpu: "CPU", value: int) -> None:
    if cpu.flags.d:
        result = _sbc_decimal(cpu, value)
    else:
        result = _adc_binary(cpu, (~value) & 0xFF)
    cpu.a = result & 0xFF


def sbc(cpu: "CPU", address: int) -> int:
    _apply_sbc(cpu, cpu.bus.read8(address))
    return 0


# --- increment / decrement ---------------------------------------------

def inc(cpu: "CPU", address: int) -> int:
    value = (cpu.bus.read8(address) + 1) & 0xFF
    cpu.bus.write8(address, value)
    cpu.set_zn(value)
    return 0


def dec(cpu: "CPU", address: int) -> int:
    value = (cpu.bus.read8(address) - 1) & 0xFF
    cpu.bus.write8(address, value)
    cpu.set_zn(value)
    return 0


def inx(cpu: "CPU", address: Optional[int]) -> int:
    cpu.x = (cpu.x + 1) & 0xFF
    cpu.set_zn(cpu.x)
    return 0


def iny(cpu: "CPU", address: Optional[int]) -> int:
    cpu.y = (cpu.y + 1) & 0xFF
    cpu.set_zn(cpu.y)
    return 0


def dex(cpu: "CPU", address: Optional[int]) -> int:
    cpu.x = (cpu.x - 1) & 0xFF
    cpu.set_zn(cpu.x)
    return 0


def dey(cpu: "CPU", address: Optional[int]) -> int:
    cpu.y = (cpu.y - 1) & 0xFF
    cpu.set_zn(cpu.y)
    return 0


# --- shifts / rotates -------------------------------------------------

def _load_operand(cpu: "CPU", address: Optional[int]) -> int:
    return cpu.a if address is None else cpu.bus.read8(address)


def _store_operand(cpu: "CPU", address: Optional[int], value: int) -> None:
    if address is None:
        cpu.a = value & 0xFF
    else:
        cpu.bus.write8(address, value & 0xFF)


def asl(cpu: "CPU", address: Optional[int]) -> int:
    value = _load_operand(cpu, address)
    cpu.flags.c = bool(value & 0x80)
    result = (value << 1) & 0xFF
    _store_operand(cpu, address, result)
    cpu.set_zn(result)
    return 0


def lsr(cpu: "CPU", address: Optional[int]) -> int:
    value = _load_operand(cpu, address)
    cpu.flags.c = bool(value & 0x01)
    result = (value >> 1) & 0xFF
    _store_operand(cpu, address, result)
    cpu.set_zn(result)
    return 0


def rol(cpu: "CPU", address: Optional[int]) -> int:
    value = _load_operand(cpu, address)
    carry_in = 1 if cpu.flags.c else 0
    cpu.flags.c = bool(value & 0x80)
    result = ((value << 1) | carry_in) & 0xFF
    _store_operand(cpu, address, result)
    cpu.set_zn(result)
    return 0


def ror(cpu: "CPU", address: Optional[int]) -> int:
    value = _load_operand(cpu, address)
    carry_in = 0x80 if cpu.flags.c else 0
    cpu.flags.c = bool(value & 0x01)
    result = (value >> 1) | carry_in
    _store_operand(cpu, address, result)
    cpu.set_zn(result)
    return 0


# --- compares ------------------------------------------------------------

def _compare_value(cpu: "CPU", register_value: int, value: int) -> None:
    diff = (register_value - value) & 0xFF
    cpu.flags.c = register_value >= value
    cpu.flags.z = register_value == value
    cpu.flags.n = bool(diff & 0x80)


def _compare(cpu: "CPU", register_value: int, address: int) -> int:
    _compare_value(cpu, register_value, cpu.bus.read8(address))
    return 0


def cmp(cpu: "CPU", address: int) -> int:
    return _compare(cpu, cpu.a, address)


def cpx(cpu: "CPU", address: int) -> int:
    return _compare(cpu, cpu.x, address)


def cpy(cpu: "CPU", address: int) -> int:
    return _compare(cpu, cpu.y, address)


# --- branches --------------------------------------------------------------

def _make_branch(taken):
    def branch(cpu: "CPU", address: int) -> int:
        if not taken(cpu.flags):
            return 0
        old_pc = cpu.pc
        extra = 1
        if (old_pc & 0xFF00) != (address & 0xFF00):
            extra += 1
        cpu.pc = address
        return extra

    return branch


beq = _make_branch(lambda f: f.z)
bne = _make_branch(lambda f: not f.z)
bcs = _make_branch(lambda f: f.c)
bcc = _make_branch(lambda f: not f.c)
bmi = _make_branch(lambda f: f.n)
bpl = _make_branch(lambda f: not f.n)
bvs = _make_branch(lambda f: f.v)
bvc = _make_branch(lambda f: not f.v)


# --- jumps -------------------------------------------------------------

def jmp(cpu: "CPU", address: int) -> int:
    cpu.pc = address
    return 0


def jsr(cpu: "CPU", address: int) -> int:
    # JSR pushes the address of its own last byte, not the next instruction
    # -- RTS pulls it back and adds 1.
    cpu.push16((cpu.pc - 1) & 0xFFFF)
    cpu.pc = address
    return 0


def rts(cpu: "CPU", address: Optional[int]) -> int:
    cpu.pc = (cpu.pull16() + 1) & 0xFFFF
    return 0


# --- flag ops / NOP -----------------------------------------------------

def clc(cpu: "CPU", address: Optional[int]) -> int:
    cpu.flags.c = False
    return 0


def sec(cpu: "CPU", address: Optional[int]) -> int:
    cpu.flags.c = True
    return 0


def cli(cpu: "CPU", address: Optional[int]) -> int:
    cpu.flags.i = False
    return 0


def sei(cpu: "CPU", address: Optional[int]) -> int:
    cpu.flags.i = True
    return 0


def cld(cpu: "CPU", address: Optional[int]) -> int:
    cpu.flags.d = False
    return 0


def sed(cpu: "CPU", address: Optional[int]) -> int:
    cpu.flags.d = True
    return 0


def clv(cpu: "CPU", address: Optional[int]) -> int:
    cpu.flags.v = False
    return 0


def nop(cpu: "CPU", address: Optional[int]) -> int:
    return 0


# --- software interrupts ------------------------------------------------

def brk(cpu: "CPU", address: Optional[int]) -> int:
    cpu.pc = (cpu.pc + 1) & 0xFFFF  # skip the padding/signature byte
    cpu.push16(cpu.pc)
    cpu.push8(cpu.flags.pack(brk=True))
    cpu.flags.i = True
    cpu.pc = cpu._read16(IRQ_VECTOR)
    return 0


def rti(cpu: "CPU", address: Optional[int]) -> int:
    cpu.flags.unpack(cpu.pull8())
    cpu.pc = cpu.pull16()
    return 0


# --- illegal/undocumented opcodes ---------------------------------------
# See opcodes.py's "illegal/undocumented opcodes" section and
# docs/6502-reference.md for citations. These are the subset with reliable,
# deterministic behavior on real NMOS 6502/6510 hardware -- the remaining
# chip-unstable ones (ANE/XAA, LXA, LAS, SHA, SHX, SHY, TAS) are
# deliberately not implemented (see cpu.py's IllegalOpcodeError).

def lax(cpu: "CPU", address: int) -> int:
    """LDA+LDX combined: loads the same value into both A and X."""
    value = cpu.bus.read8(address)
    cpu.a = value
    cpu.x = value
    cpu.set_zn(value)
    return 0


def sax(cpu: "CPU", address: int) -> int:
    """Stores A AND X -- unlike the ALU ops below, this touches no flags."""
    cpu.bus.write8(address, cpu.a & cpu.x)
    return 0


def dcp(cpu: "CPU", address: int) -> int:
    """DEC memory, then CMP A against the decremented value."""
    value = (cpu.bus.read8(address) - 1) & 0xFF
    cpu.bus.write8(address, value)
    _compare_value(cpu, cpu.a, value)
    return 0


def isc(cpu: "CPU", address: int) -> int:
    """INC memory, then SBC A against the incremented value."""
    value = (cpu.bus.read8(address) + 1) & 0xFF
    cpu.bus.write8(address, value)
    _apply_sbc(cpu, value)
    return 0


def slo(cpu: "CPU", address: int) -> int:
    """ASL memory, then ORA A with the shifted value."""
    value = cpu.bus.read8(address)
    cpu.flags.c = bool(value & 0x80)
    result = (value << 1) & 0xFF
    cpu.bus.write8(address, result)
    cpu.a |= result
    cpu.set_zn(cpu.a)
    return 0


def rla(cpu: "CPU", address: int) -> int:
    """ROL memory, then AND A with the rotated value."""
    value = cpu.bus.read8(address)
    carry_in = 1 if cpu.flags.c else 0
    cpu.flags.c = bool(value & 0x80)
    result = ((value << 1) | carry_in) & 0xFF
    cpu.bus.write8(address, result)
    cpu.a &= result
    cpu.set_zn(cpu.a)
    return 0


def sre(cpu: "CPU", address: int) -> int:
    """LSR memory, then EOR A with the shifted value."""
    value = cpu.bus.read8(address)
    cpu.flags.c = bool(value & 0x01)
    result = (value >> 1) & 0xFF
    cpu.bus.write8(address, result)
    cpu.a ^= result
    cpu.set_zn(cpu.a)
    return 0


def rra(cpu: "CPU", address: int) -> int:
    """ROR memory, then ADC A with the rotated value -- the carry the ROR
    produces feeds directly into the ADC's carry-in, same as real hardware
    (both steps share the same flags.c, mutated in place)."""
    value = cpu.bus.read8(address)
    carry_in = 0x80 if cpu.flags.c else 0
    cpu.flags.c = bool(value & 0x01)
    result = (value >> 1) | carry_in
    cpu.bus.write8(address, result)
    _apply_adc(cpu, result)
    return 0


def anc(cpu: "CPU", address: int) -> int:
    """AND A with the operand, then copy the result's sign bit into carry
    (as if it had gone through ASL/ROL) -- both $0B and $2B are this."""
    cpu.a &= cpu.bus.read8(address)
    cpu.set_zn(cpu.a)
    cpu.flags.c = bool(cpu.a & 0x80)
    return 0


def alr(cpu: "CPU", address: int) -> int:
    """AND A with the operand, then LSR the accumulator."""
    cpu.a &= cpu.bus.read8(address)
    cpu.flags.c = bool(cpu.a & 0x01)
    cpu.a = (cpu.a >> 1) & 0xFF
    cpu.set_zn(cpu.a)
    return 0


def arr(cpu: "CPU", address: int) -> int:
    """AND A with the operand, then ROR the accumulator, with C/V set from
    bits 6/5 of the result rather than the usual ROR-carry-out rule.

    This is the widely-documented binary-mode formula. Real NMOS hardware
    has an additional decimal-mode-dependent wrinkle here (like ADC/SBC's
    own quirky decimal flag behavior, see _adc_decimal's note) that this
    does not reproduce -- a disclosed gap, not an oversight, since ARR in
    decimal mode is vanishingly rare in real C64 software.
    """
    cpu.a &= cpu.bus.read8(address)
    carry_in = 0x80 if cpu.flags.c else 0
    cpu.a = ((cpu.a >> 1) | carry_in) & 0xFF
    cpu.set_zn(cpu.a)
    bit6 = bool(cpu.a & 0x40)
    bit5 = bool(cpu.a & 0x20)
    cpu.flags.c = bit6
    cpu.flags.v = bit6 != bit5
    return 0


def sbx(cpu: "CPU", address: int) -> int:
    """(A AND X) - operand -> X, flags set like CMP (a fused CMP+DEX)."""
    value = cpu.bus.read8(address)
    combined = cpu.a & cpu.x
    cpu.x = (combined - value) & 0xFF
    cpu.flags.c = combined >= value
    cpu.set_zn(cpu.x)
    return 0


def jam(cpu: "CPU", address: Optional[int]) -> int:
    """JAM/KIL/HLT: on real hardware this locks the CPU in an internal
    fetch cycle indefinitely -- there's no instruction to "finish", only a
    reset gets it out. Modeled as a distinct, loud failure rather than a
    silent infinite loop or folding into IllegalOpcodeError, since this is
    documented, real opcode behavior, not something unimplemented."""
    from .cpu import ProcessorJammed  # deferred: avoids a cpu<->instructions import cycle

    opcode_pc = (cpu.pc - 1) & 0xFFFF
    raise ProcessorJammed(cpu.bus.read8(opcode_pc), opcode_pc)
