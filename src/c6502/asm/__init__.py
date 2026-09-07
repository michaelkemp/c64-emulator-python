"""6502 assembler, ported unchanged from c-compiler-6502.

Turns 6502 assembly source into a flat binary image (AssembledImage).
General-purpose, not tied to any particular memory map -- once this
project has a real C64 Bus (src/c64/), its load_rom()-equivalent should
accept an AssembledImage the same way. See the source repo's
docs/roadmap.md (Phase 4) for the supported syntax and the deliberate
"labels always assemble as absolute addressing" simplification -- that
design reasoning didn't get copied here verbatim, but the module
docstrings below still explain the behavior itself.

Modules:
    expr.py      -- number/char literal parsing, label+offset expressions
    encoding.py  -- (mnemonic, mode) -> opcode byte, derived from
                    c6502.emulator.opcodes.OPCODES
    operands.py  -- operand syntax -> addressing mode
    assembler.py -- the two-pass driver: assemble(source) -> AssembledImage
"""

from .assembler import AssembledImage, assemble
from .errors import AssemblerError

__all__ = ["assemble", "AssembledImage", "AssemblerError"]
