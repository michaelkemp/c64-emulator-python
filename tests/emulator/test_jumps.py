from .helpers import run_at


def test_jmp_absolute(cpu):
    run_at(cpu, 0x0200, 0x4C, 0x00, 0x03)
    assert cpu.pc == 0x0300


def test_jmp_indirect(cpu):
    cpu.bus.write16(0x0300, 0x0400)
    run_at(cpu, 0x0200, 0x6C, 0x00, 0x03)
    assert cpu.pc == 0x0400


def test_jmp_indirect_page_wrap_bug(cpu):
    # Famous NMOS bug: JMP ($xxFF) fetches the high byte from $xx00, not
    # $(xx+1)00. Reproduced deliberately -- see docs/6502-reference.md.
    cpu.bus.write8(0x02FF, 0x00)  # low byte of target
    cpu.bus.write8(0x0300, 0x99)  # what a "correct" wrap would read (wrong)
    cpu.bus.write8(0x0200, 0x11)  # what NMOS actually reads (page wraps)
    result = run_at(cpu, 0x0400, 0x6C, 0xFF, 0x02)
    assert cpu.pc == 0x1100


def test_jsr_rts_round_trip(cpu):
    run_at(cpu, 0x0200, 0x20, 0x00, 0x03)  # JSR $0300
    assert cpu.pc == 0x0300
    run_at(cpu, 0x0300, 0x60)  # RTS
    assert cpu.pc == 0x0203  # back to the instruction right after the JSR
