"""Shared helpers for CPU unit tests."""


def load(bus, address, *values):
    for offset, value in enumerate(values):
        bus.write8((address + offset) & 0xFFFF, value)


def run_at(cpu, address, *opcode_bytes):
    """Load opcode_bytes at address, point PC there, and execute one step."""
    load(cpu.bus, address, *opcode_bytes)
    cpu.pc = address
    return cpu.step()
