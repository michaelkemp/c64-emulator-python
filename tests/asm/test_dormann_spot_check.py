"""Spot-checks our assembler's output against real bytes from Klaus
Dormann's pre-assembled 6502_functional_test.bin (verified in Phase 3 --
see docs/testing-strategy.md). We can't feed that suite's actual .a65
source into our assembler (it uses macros and conditional assembly our
minimal Phase 4 assembler deliberately doesn't support), but we can
hand-transcribe its first few real instructions in our own syntax and
confirm we produce byte-for-byte the same machine code a real assembler
(AS65) produced for the same program -- a genuine cross-check against an
independent, trusted source, not just our own opcode table talking to
itself.

The 16 expected bytes below were read directly from
tests/emulator/fixtures/dormann/6502_functional_test.bin at file offset
$0400 during Phase 3's research (`xxd -s 0x400 -l 16`), decoded by hand
against the suite's listing (6502_functional_test.lst):
    $0400  d8         CLD
    $0401  a2 ff      LDX #$FF
    $0403  9a         TXS
    $0404  a9 00      LDA #$00
    $0406  8d 00 02   STA $0200
    $0409  a2 05      LDX #$05
    $040b  4c 33 04   JMP $0433
    $040e  a0 05      LDY #$05
"""

from c6502.asm import assemble

_SOURCE = """
    .org $0400
start:
    CLD
    LDX #$FF
    TXS
    LDA #$00
    STA $0200
    LDX #$05
    JMP $0433
    LDY #$05
"""

_EXPECTED = bytes.fromhex("d8a2ff9aa9008d0002a2054c3304a005")


def test_matches_real_dormann_test_bytes():
    image = assemble(_SOURCE)
    assert image.origin == 0x0400
    assert image.data == _EXPECTED
