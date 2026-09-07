from .helpers import run_at


def test_branch_not_taken_costs_two_cycles_and_falls_through(cpu):
    cpu.flags.z = False
    result = run_at(cpu, 0x0200, 0xF0, 0x10)  # BEQ +$10, Z clear
    assert result.cycles == 2
    assert cpu.pc == 0x0202


def test_branch_taken_same_page_costs_three_cycles(cpu):
    cpu.flags.z = True
    result = run_at(cpu, 0x0200, 0xF0, 0x10)  # BEQ +$10, Z set
    assert result.cycles == 3
    assert cpu.pc == 0x0212  # 0x0202 (next instr) + 0x10


def test_branch_taken_crossing_page_costs_four_cycles(cpu):
    cpu.flags.c = False
    # BCC at $02F0 with a +$20 offset: next-instr PC is $02F2, target $0312
    # -- crosses from page $02 to $03.
    result = run_at(cpu, 0x02F0, 0x90, 0x20)
    assert result.cycles == 4
    assert cpu.pc == 0x0312


def test_bne_bmi_bpl_bvc_bvs_bcs(cpu):
    cpu.flags.z = True
    run_at(cpu, 0x0200, 0xD0, 0x10)  # BNE, Z set -> not taken
    assert cpu.pc == 0x0202

    cpu.flags.n = True
    run_at(cpu, 0x0210, 0x30, 0x02)  # BMI, N set -> taken
    assert cpu.pc == 0x0214

    cpu.flags.n = True
    run_at(cpu, 0x0220, 0x10, 0x02)  # BPL, N set -> not taken
    assert cpu.pc == 0x0222

    cpu.flags.v = False
    run_at(cpu, 0x0230, 0x50, 0x02)  # BVC, V clear -> taken
    assert cpu.pc == 0x0234

    cpu.flags.v = True
    run_at(cpu, 0x0240, 0x70, 0x02)  # BVS, V set -> taken
    assert cpu.pc == 0x0244

    cpu.flags.c = True
    run_at(cpu, 0x0250, 0xB0, 0x02)  # BCS, C set -> taken
    assert cpu.pc == 0x0254
