"""NMOS 6502 CPU core, ported unchanged from c-compiler-6502.

cpu.py (CPU/Flags/StepResult), addressing.py, instructions.py, opcodes.py
(the OPCODES dispatch table), trace.py (step trace line formatting),
vectors.py, bus.py (FlatMemory only -- see its own module docstring for
why the rest of that file didn't come along).

This code already passed Klaus Dormann's functional test suite in the
source repo (30,646,177 steps, traps at the documented success address)
-- see CLAUDE.md for how to re-validate that here. Treat it as trustworthy,
finished infrastructure, not something to redesign; the real C64-specific
work (VIC-II, SID, CIA, the real memory map) belongs in src/c64/.
"""
