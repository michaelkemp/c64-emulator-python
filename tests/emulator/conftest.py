import pytest

from c6502.emulator.bus import FlatMemory
from c6502.emulator.cpu import CPU


@pytest.fixture
def bus():
    return FlatMemory()


@pytest.fixture
def cpu(bus):
    c = CPU(bus)
    c.reset()
    return c
