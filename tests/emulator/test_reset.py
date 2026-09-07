from c6502.emulator.cpu import CPU


def test_reset_loads_pc_from_reset_vector(bus):
    bus.write16(0xFFFC, 0x1234)
    cpu = CPU(bus)
    cpu.reset()
    assert cpu.pc == 0x1234


def test_reset_sets_known_register_state(bus):
    bus.write16(0xFFFC, 0x8000)
    cpu = CPU(bus)
    cpu.a = 0xAA
    cpu.x = 0xBB
    cpu.y = 0xCC
    cpu.reset()
    assert (cpu.a, cpu.x, cpu.y) == (0, 0, 0)
    assert cpu.sp == 0xFD
    assert cpu.flags.i is True
    assert cpu.flags.pack(brk=False) & 0x20  # bit 5 always reads as 1
