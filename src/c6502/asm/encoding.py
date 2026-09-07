"""Reverse opcode encoding, derived from the emulator's OPCODES table.

Building (mnemonic, mode) -> opcode byte by inverting
c6502.emulator.opcodes.OPCODES (rather than hand-writing a second opcode
table here) guarantees the assembler can never encode something the CPU
core doesn't also decode -- they share one source of truth.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Tuple

from c6502.emulator.opcodes import OPCODES

# (mnemonic, mode) -> opcode byte
ENCODING: Dict[Tuple[str, str], int] = {
    (spec.mnemonic, spec.mode): opcode for opcode, spec in OPCODES.items()
}

# Mnemonics using relative addressing (branches) -- a bare operand means
# "branch target", not zero-page/absolute.
BRANCH_MNEMONICS: FrozenSet[str] = frozenset(
    spec.mnemonic for spec in OPCODES.values() if spec.mode == "rel"
)

# Mnemonics with an accumulator addressing mode (ASL/LSR/ROL/ROR) -- no
# operand, or an explicit "A", means "operate on the accumulator".
ACCUMULATOR_MNEMONICS: FrozenSet[str] = frozenset(
    spec.mnemonic for spec in OPCODES.values() if spec.mode == "acc"
)


def has_mode(mnemonic: str, mode: str) -> bool:
    return (mnemonic, mode) in ENCODING


def opcode_for(mnemonic: str, mode: str) -> int:
    return ENCODING[(mnemonic, mode)]
