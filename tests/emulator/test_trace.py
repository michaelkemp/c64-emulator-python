from c6502.emulator.trace import format_step

from .helpers import run_at


def test_format_step_immediate_instruction(cpu):
    result = run_at(cpu, 0x0200, 0xA9, 0x05)  # LDA #$05
    line = format_step(result)
    assert line.startswith("0200  A9 05     LDA #$05")
    assert "A:05" in line
    assert "CYC:2" in line


def test_format_step_branch_shows_target_address(cpu):
    cpu.flags.z = True
    result = run_at(cpu, 0x0200, 0xF0, 0x10)  # BEQ, taken
    line = format_step(result)
    assert "BEQ $0212" in line
