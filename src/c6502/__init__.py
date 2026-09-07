"""NMOS 6502 CPU core + assembler, ported unchanged from c-compiler-6502.

See that repo (github.com/michaelkemp/c-compiler-6502) for the emulator
project this was originally built for, and this repo's own CLAUDE.md for
why it was carried over and what's built on top of it here.

Submodules:
    emulator -- CPU core, opcode table, flat test memory (see its own
                __init__.py for exactly what came along)
    asm      -- 6502 assembler
"""
