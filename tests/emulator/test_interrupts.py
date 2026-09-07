from .helpers import run_at


def test_brk_pushes_pc_and_flags_then_jumps_to_irq_vector(cpu):
    cpu.bus.write16(0xFFFE, 0x9000)
    result = run_at(cpu, 0x0200, 0x00, 0x00)  # BRK (+ padding byte)
    assert cpu.pc == 0x9000
    assert cpu.flags.i is True
    assert result.cycles == 7

    pushed_p = cpu.bus.read8(0x0100 + cpu.sp + 1)
    assert pushed_p & 0x10  # break bit set on a BRK push

    pushed_pc = cpu.bus.read8(0x0100 + cpu.sp + 2) | (
        cpu.bus.read8(0x0100 + cpu.sp + 3) << 8
    )
    assert pushed_pc == 0x0202  # PC after BRK's two bytes


def test_rti_restores_flags_and_pc(cpu):
    cpu.bus.write16(0xFFFE, 0x9000)
    run_at(cpu, 0x0200, 0x00, 0x00)  # BRK
    run_at(cpu, cpu.pc, 0x40)  # RTI
    assert cpu.pc == 0x0202
    assert cpu.flags.i is True  # I was set by BRK, restored as pushed


def test_irq_ignored_when_interrupt_disable_set(cpu):
    cpu.flags.i = True
    cpu.pc = 0x0500
    cpu.irq()
    assert cpu.pc == 0x0500  # unchanged: IRQ is masked


def test_irq_taken_when_interrupt_disable_clear(cpu):
    cpu.bus.write16(0xFFFE, 0xA000)
    cpu.flags.i = False
    cpu.pc = 0x0500
    cpu.irq()
    assert cpu.pc == 0xA000
    assert cpu.flags.i is True


def test_nmi_always_taken_regardless_of_interrupt_disable(cpu):
    cpu.bus.write16(0xFFFA, 0xB000)
    cpu.flags.i = True
    cpu.pc = 0x0500
    cpu.nmi()
    assert cpu.pc == 0xB000
