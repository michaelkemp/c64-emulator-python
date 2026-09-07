"""End-to-end proof: real assembly source -> assemble() -> CPU -> real
memory contents. Adapted from c-compiler-6502's version of this test,
which used that repo's Machine/AciaDevice (a serial console specific to
that project's own board) -- this repo doesn't have those, so this
version asserts on a memory location directly instead of console output.
Same underlying proof: the assembler's output is byte-correct machine
code that the CPU core actually executes correctly.
"""

from c6502.asm import assemble
from c6502.emulator.bus import FlatMemory
from c6502.emulator.cpu import CPU

_SOURCE = """
    .org $8000
start:
    LDA #$05
    STA $10
    LDA #$07
    ADC $10
    STA $11
loop:
    JMP loop

    .org $FFFC
    .word start
"""


def test_assembled_program_runs_on_the_cpu():
    image = assemble(_SOURCE)

    memory = FlatMemory()
    memory.load(image.origin, image.data)

    cpu = CPU(memory)
    cpu.reset()
    assert cpu.pc == 0x8000  # reset vector picked up "start"

    for _ in range(5):  # LDA, STA, LDA, ADC, STA -- stop before the JMP loop
        cpu.step()

    assert memory.read8(0x10) == 0x05
    assert memory.read8(0x11) == 0x0C  # 5 + 7
