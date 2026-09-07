"""Locks in the guarantee that motivated encoding.py's design: since
ENCODING is derived by inverting c6502.emulator.opcodes.OPCODES (rather
than a hand-written second table), every opcode the assembler can emit is
exactly one the CPU core already decodes -- and that CPU core has already
passed Klaus Dormann's functional test suite (see
tests/emulator/test_dormann_functional.py). This test protects that
guarantee against someone later "fixing" encoding.py with a hand-written
table that quietly drifts out of sync.
"""

from c6502.asm.encoding import opcode_for
from c6502.emulator.opcodes import OPCODES


def test_every_legal_opcode_round_trips_through_the_assembler_encoding():
    for opcode, spec in OPCODES.items():
        assert opcode_for(spec.mnemonic, spec.mode) == opcode
