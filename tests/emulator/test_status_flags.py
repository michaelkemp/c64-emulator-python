from .helpers import run_at


def test_clc_sec(cpu):
    cpu.flags.c = True
    run_at(cpu, 0x0200, 0x18)  # CLC
    assert cpu.flags.c is False
    run_at(cpu, 0x0201, 0x38)  # SEC
    assert cpu.flags.c is True


def test_cli_sei(cpu):
    cpu.flags.i = True
    run_at(cpu, 0x0200, 0x58)  # CLI
    assert cpu.flags.i is False
    run_at(cpu, 0x0201, 0x78)  # SEI
    assert cpu.flags.i is True


def test_cld_sed(cpu):
    cpu.flags.d = False
    run_at(cpu, 0x0200, 0xF8)  # SED
    assert cpu.flags.d is True
    run_at(cpu, 0x0201, 0xD8)  # CLD
    assert cpu.flags.d is False


def test_clv(cpu):
    cpu.flags.v = True
    run_at(cpu, 0x0200, 0xB8)  # CLV
    assert cpu.flags.v is False


def test_nop_only_advances_pc(cpu):
    cpu.a, cpu.x, cpu.y = 1, 2, 3
    result = run_at(cpu, 0x0200, 0xEA)  # NOP
    assert (cpu.a, cpu.x, cpu.y) == (1, 2, 3)
    assert cpu.pc == 0x0201
    assert result.cycles == 2
