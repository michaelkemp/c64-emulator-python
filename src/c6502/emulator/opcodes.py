"""Opcode dispatch table for the NMOS 6502.

Pure data + wiring: OPCODES maps each legal opcode byte to an OpcodeSpec
naming its mnemonic, addressing mode, the addressing/instruction functions
that implement it, and its cycle count. Undocumented/"illegal" opcodes are
deliberately absent -- see cpu.py's IllegalOpcodeError.

Cycle counts and the addressing-mode matrix per instruction are cross-
checked against https://masswerk.at/6502/6502_instruction_set.html (see
docs/6502-reference.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

from . import addressing as am
from . import instructions as instr


@dataclass(frozen=True)
class OpcodeSpec:
    mnemonic: str
    mode: str
    addressing_fn: Callable
    instruction_fn: Callable
    base_cycles: int
    extra_on_page_cross: bool = False


OPCODES: Dict[int, OpcodeSpec] = {}


def _add(
    opcode: int,
    mnemonic: str,
    mode: str,
    addressing_fn: Callable,
    instruction_fn: Callable,
    base_cycles: int,
    extra_on_page_cross: bool = False,
) -> None:
    if opcode in OPCODES:
        raise ValueError(f"duplicate opcode ${opcode:02X}")
    OPCODES[opcode] = OpcodeSpec(
        mnemonic, mode, addressing_fn, instruction_fn, base_cycles, extra_on_page_cross
    )


# --- loads ---------------------------------------------------------------

_add(0xA9, "LDA", "imm", am.immediate, instr.lda, 2)
_add(0xA5, "LDA", "zp", am.zero_page, instr.lda, 3)
_add(0xB5, "LDA", "zpx", am.zero_page_x, instr.lda, 4)
_add(0xAD, "LDA", "abs", am.absolute, instr.lda, 4)
_add(0xBD, "LDA", "absx", am.absolute_x, instr.lda, 4, extra_on_page_cross=True)
_add(0xB9, "LDA", "absy", am.absolute_y, instr.lda, 4, extra_on_page_cross=True)
_add(0xA1, "LDA", "indx", am.indexed_indirect, instr.lda, 6)
_add(0xB1, "LDA", "indy", am.indirect_indexed, instr.lda, 5, extra_on_page_cross=True)

_add(0xA2, "LDX", "imm", am.immediate, instr.ldx, 2)
_add(0xA6, "LDX", "zp", am.zero_page, instr.ldx, 3)
_add(0xB6, "LDX", "zpy", am.zero_page_y, instr.ldx, 4)
_add(0xAE, "LDX", "abs", am.absolute, instr.ldx, 4)
_add(0xBE, "LDX", "absy", am.absolute_y, instr.ldx, 4, extra_on_page_cross=True)

_add(0xA0, "LDY", "imm", am.immediate, instr.ldy, 2)
_add(0xA4, "LDY", "zp", am.zero_page, instr.ldy, 3)
_add(0xB4, "LDY", "zpx", am.zero_page_x, instr.ldy, 4)
_add(0xAC, "LDY", "abs", am.absolute, instr.ldy, 4)
_add(0xBC, "LDY", "absx", am.absolute_x, instr.ldy, 4, extra_on_page_cross=True)

# --- stores (always take the "worst case" cycles -- no page-cross saving) --

_add(0x85, "STA", "zp", am.zero_page, instr.sta, 3)
_add(0x95, "STA", "zpx", am.zero_page_x, instr.sta, 4)
_add(0x8D, "STA", "abs", am.absolute, instr.sta, 4)
_add(0x9D, "STA", "absx", am.absolute_x, instr.sta, 5)
_add(0x99, "STA", "absy", am.absolute_y, instr.sta, 5)
_add(0x81, "STA", "indx", am.indexed_indirect, instr.sta, 6)
_add(0x91, "STA", "indy", am.indirect_indexed, instr.sta, 6)

_add(0x86, "STX", "zp", am.zero_page, instr.stx, 3)
_add(0x96, "STX", "zpy", am.zero_page_y, instr.stx, 4)
_add(0x8E, "STX", "abs", am.absolute, instr.stx, 4)

_add(0x84, "STY", "zp", am.zero_page, instr.sty, 3)
_add(0x94, "STY", "zpx", am.zero_page_x, instr.sty, 4)
_add(0x8C, "STY", "abs", am.absolute, instr.sty, 4)

# --- transfers / stack (all implied) --------------------------------------

_add(0xAA, "TAX", "impl", am.implied, instr.tax, 2)
_add(0xA8, "TAY", "impl", am.implied, instr.tay, 2)
_add(0x8A, "TXA", "impl", am.implied, instr.txa, 2)
_add(0x98, "TYA", "impl", am.implied, instr.tya, 2)
_add(0xBA, "TSX", "impl", am.implied, instr.tsx, 2)
_add(0x9A, "TXS", "impl", am.implied, instr.txs, 2)

_add(0x48, "PHA", "impl", am.implied, instr.pha, 3)
_add(0x68, "PLA", "impl", am.implied, instr.pla, 4)
_add(0x08, "PHP", "impl", am.implied, instr.php, 3)
_add(0x28, "PLP", "impl", am.implied, instr.plp, 4)

# --- logic ---------------------------------------------------------------

_add(0x29, "AND", "imm", am.immediate, instr.and_, 2)
_add(0x25, "AND", "zp", am.zero_page, instr.and_, 3)
_add(0x35, "AND", "zpx", am.zero_page_x, instr.and_, 4)
_add(0x2D, "AND", "abs", am.absolute, instr.and_, 4)
_add(0x3D, "AND", "absx", am.absolute_x, instr.and_, 4, extra_on_page_cross=True)
_add(0x39, "AND", "absy", am.absolute_y, instr.and_, 4, extra_on_page_cross=True)
_add(0x21, "AND", "indx", am.indexed_indirect, instr.and_, 6)
_add(0x31, "AND", "indy", am.indirect_indexed, instr.and_, 5, extra_on_page_cross=True)

_add(0x09, "ORA", "imm", am.immediate, instr.ora, 2)
_add(0x05, "ORA", "zp", am.zero_page, instr.ora, 3)
_add(0x15, "ORA", "zpx", am.zero_page_x, instr.ora, 4)
_add(0x0D, "ORA", "abs", am.absolute, instr.ora, 4)
_add(0x1D, "ORA", "absx", am.absolute_x, instr.ora, 4, extra_on_page_cross=True)
_add(0x19, "ORA", "absy", am.absolute_y, instr.ora, 4, extra_on_page_cross=True)
_add(0x01, "ORA", "indx", am.indexed_indirect, instr.ora, 6)
_add(0x11, "ORA", "indy", am.indirect_indexed, instr.ora, 5, extra_on_page_cross=True)

_add(0x49, "EOR", "imm", am.immediate, instr.eor, 2)
_add(0x45, "EOR", "zp", am.zero_page, instr.eor, 3)
_add(0x55, "EOR", "zpx", am.zero_page_x, instr.eor, 4)
_add(0x4D, "EOR", "abs", am.absolute, instr.eor, 4)
_add(0x5D, "EOR", "absx", am.absolute_x, instr.eor, 4, extra_on_page_cross=True)
_add(0x59, "EOR", "absy", am.absolute_y, instr.eor, 4, extra_on_page_cross=True)
_add(0x41, "EOR", "indx", am.indexed_indirect, instr.eor, 6)
_add(0x51, "EOR", "indy", am.indirect_indexed, instr.eor, 5, extra_on_page_cross=True)

_add(0x24, "BIT", "zp", am.zero_page, instr.bit, 3)
_add(0x2C, "BIT", "abs", am.absolute, instr.bit, 4)

# --- arithmetic ------------------------------------------------------------

_add(0x69, "ADC", "imm", am.immediate, instr.adc, 2)
_add(0x65, "ADC", "zp", am.zero_page, instr.adc, 3)
_add(0x75, "ADC", "zpx", am.zero_page_x, instr.adc, 4)
_add(0x6D, "ADC", "abs", am.absolute, instr.adc, 4)
_add(0x7D, "ADC", "absx", am.absolute_x, instr.adc, 4, extra_on_page_cross=True)
_add(0x79, "ADC", "absy", am.absolute_y, instr.adc, 4, extra_on_page_cross=True)
_add(0x61, "ADC", "indx", am.indexed_indirect, instr.adc, 6)
_add(0x71, "ADC", "indy", am.indirect_indexed, instr.adc, 5, extra_on_page_cross=True)

_add(0xE9, "SBC", "imm", am.immediate, instr.sbc, 2)
_add(0xE5, "SBC", "zp", am.zero_page, instr.sbc, 3)
_add(0xF5, "SBC", "zpx", am.zero_page_x, instr.sbc, 4)
_add(0xED, "SBC", "abs", am.absolute, instr.sbc, 4)
_add(0xFD, "SBC", "absx", am.absolute_x, instr.sbc, 4, extra_on_page_cross=True)
_add(0xF9, "SBC", "absy", am.absolute_y, instr.sbc, 4, extra_on_page_cross=True)
_add(0xE1, "SBC", "indx", am.indexed_indirect, instr.sbc, 6)
_add(0xF1, "SBC", "indy", am.indirect_indexed, instr.sbc, 5, extra_on_page_cross=True)

# --- increment / decrement (memory always "worst case", implied are fixed) -

_add(0xE6, "INC", "zp", am.zero_page, instr.inc, 5)
_add(0xF6, "INC", "zpx", am.zero_page_x, instr.inc, 6)
_add(0xEE, "INC", "abs", am.absolute, instr.inc, 6)
_add(0xFE, "INC", "absx", am.absolute_x, instr.inc, 7)

_add(0xC6, "DEC", "zp", am.zero_page, instr.dec, 5)
_add(0xD6, "DEC", "zpx", am.zero_page_x, instr.dec, 6)
_add(0xCE, "DEC", "abs", am.absolute, instr.dec, 6)
_add(0xDE, "DEC", "absx", am.absolute_x, instr.dec, 7)

_add(0xE8, "INX", "impl", am.implied, instr.inx, 2)
_add(0xC8, "INY", "impl", am.implied, instr.iny, 2)
_add(0xCA, "DEX", "impl", am.implied, instr.dex, 2)
_add(0x88, "DEY", "impl", am.implied, instr.dey, 2)

# --- shifts / rotates -------------------------------------------------

_add(0x0A, "ASL", "acc", am.accumulator, instr.asl, 2)
_add(0x06, "ASL", "zp", am.zero_page, instr.asl, 5)
_add(0x16, "ASL", "zpx", am.zero_page_x, instr.asl, 6)
_add(0x0E, "ASL", "abs", am.absolute, instr.asl, 6)
_add(0x1E, "ASL", "absx", am.absolute_x, instr.asl, 7)

_add(0x4A, "LSR", "acc", am.accumulator, instr.lsr, 2)
_add(0x46, "LSR", "zp", am.zero_page, instr.lsr, 5)
_add(0x56, "LSR", "zpx", am.zero_page_x, instr.lsr, 6)
_add(0x4E, "LSR", "abs", am.absolute, instr.lsr, 6)
_add(0x5E, "LSR", "absx", am.absolute_x, instr.lsr, 7)

_add(0x2A, "ROL", "acc", am.accumulator, instr.rol, 2)
_add(0x26, "ROL", "zp", am.zero_page, instr.rol, 5)
_add(0x36, "ROL", "zpx", am.zero_page_x, instr.rol, 6)
_add(0x2E, "ROL", "abs", am.absolute, instr.rol, 6)
_add(0x3E, "ROL", "absx", am.absolute_x, instr.rol, 7)

_add(0x6A, "ROR", "acc", am.accumulator, instr.ror, 2)
_add(0x66, "ROR", "zp", am.zero_page, instr.ror, 5)
_add(0x76, "ROR", "zpx", am.zero_page_x, instr.ror, 6)
_add(0x6E, "ROR", "abs", am.absolute, instr.ror, 6)
_add(0x7E, "ROR", "absx", am.absolute_x, instr.ror, 7)

# --- compares --------------------------------------------------------------

_add(0xC9, "CMP", "imm", am.immediate, instr.cmp, 2)
_add(0xC5, "CMP", "zp", am.zero_page, instr.cmp, 3)
_add(0xD5, "CMP", "zpx", am.zero_page_x, instr.cmp, 4)
_add(0xCD, "CMP", "abs", am.absolute, instr.cmp, 4)
_add(0xDD, "CMP", "absx", am.absolute_x, instr.cmp, 4, extra_on_page_cross=True)
_add(0xD9, "CMP", "absy", am.absolute_y, instr.cmp, 4, extra_on_page_cross=True)
_add(0xC1, "CMP", "indx", am.indexed_indirect, instr.cmp, 6)
_add(0xD1, "CMP", "indy", am.indirect_indexed, instr.cmp, 5, extra_on_page_cross=True)

_add(0xE0, "CPX", "imm", am.immediate, instr.cpx, 2)
_add(0xE4, "CPX", "zp", am.zero_page, instr.cpx, 3)
_add(0xEC, "CPX", "abs", am.absolute, instr.cpx, 4)

_add(0xC0, "CPY", "imm", am.immediate, instr.cpy, 2)
_add(0xC4, "CPY", "zp", am.zero_page, instr.cpy, 3)
_add(0xCC, "CPY", "abs", am.absolute, instr.cpy, 4)

# --- branches (base 2 cycles; +1 taken, +1 more if the branch crosses a ----
# --- page, both added by the instruction function itself) -----------------

_add(0xF0, "BEQ", "rel", am.relative, instr.beq, 2)
_add(0xD0, "BNE", "rel", am.relative, instr.bne, 2)
_add(0xB0, "BCS", "rel", am.relative, instr.bcs, 2)
_add(0x90, "BCC", "rel", am.relative, instr.bcc, 2)
_add(0x30, "BMI", "rel", am.relative, instr.bmi, 2)
_add(0x10, "BPL", "rel", am.relative, instr.bpl, 2)
_add(0x70, "BVS", "rel", am.relative, instr.bvs, 2)
_add(0x50, "BVC", "rel", am.relative, instr.bvc, 2)

# --- jumps -------------------------------------------------------------

_add(0x4C, "JMP", "abs", am.absolute, instr.jmp, 3)
_add(0x6C, "JMP", "ind", am.indirect, instr.jmp, 5)
_add(0x20, "JSR", "abs", am.absolute, instr.jsr, 6)
_add(0x60, "RTS", "impl", am.implied, instr.rts, 6)

# --- flag ops / NOP (all implied) ---------------------------------------

_add(0x18, "CLC", "impl", am.implied, instr.clc, 2)
_add(0x38, "SEC", "impl", am.implied, instr.sec, 2)
_add(0x58, "CLI", "impl", am.implied, instr.cli, 2)
_add(0x78, "SEI", "impl", am.implied, instr.sei, 2)
_add(0xD8, "CLD", "impl", am.implied, instr.cld, 2)
_add(0xF8, "SED", "impl", am.implied, instr.sed, 2)
_add(0xB8, "CLV", "impl", am.implied, instr.clv, 2)
_add(0xEA, "NOP", "impl", am.implied, instr.nop, 2)

# --- software interrupts -------------------------------------------------

_add(0x00, "BRK", "impl", am.implied, instr.brk, 7)
_add(0x40, "RTI", "impl", am.implied, instr.rti, 6)
