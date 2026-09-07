"""Validates the CPU core against Klaus Dormann's 6502 functional test
suite -- see docs/testing-strategy.md. The binary isn't vendored (it's
GPLv3); run scripts/fetch_dormann_tests.sh once to fetch it.
"""

import os

import pytest

from c6502.emulator.bus import FlatMemory
from c6502.emulator.cpu import CPU

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "dormann", "6502_functional_test.bin"
)
ENTRY_POINT = 0x0400
SUCCESS_TRAP = 0x3469
MAX_STEPS = 40_000_000  # observed 30,646,177 to succeed; headroom for a
# genuinely non-terminating bug to still fail promptly rather than hang.


@pytest.mark.slow
def test_cpu_passes_dormann_functional_suite():
    if not os.path.exists(FIXTURE_PATH):
        pytest.skip(
            "Klaus Dormann's test binary not found -- run "
            "scripts/fetch_dormann_tests.sh to fetch it (GPLv3, not vendored)."
        )

    memory = FlatMemory()
    with open(FIXTURE_PATH, "rb") as f:
        memory.load(0, f.read())

    cpu = CPU(memory)
    cpu.pc = ENTRY_POINT

    for _ in range(MAX_STEPS):
        pc_before = cpu.pc
        cpu.step()
        if cpu.pc == pc_before:
            # The suite traps (jumps to itself) on both success and every
            # failure -- the trapped address is what tells them apart.
            assert cpu.pc == SUCCESS_TRAP, (
                f"trapped at ${cpu.pc:04X}, not the success address "
                f"${SUCCESS_TRAP:04X} -- fetch the suite's .lst listing and "
                f"look up this address to identify the failing opcode/test"
            )
            return

    pytest.fail(
        f"did not trap within {MAX_STEPS} steps -- possible runaway PC "
        f"or an infinite loop that never reaches a jump-to-self trap"
    )
