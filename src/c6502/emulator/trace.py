"""Formats a StepResult as one human-readable trace line, e.g.:

    C000  A9 05     LDA #$05        A:00 X:00 Y:00 SP:FD  NV-BDIZC:00110000  CYC:2

Intentionally just a line formatter (no interactive stepping/breakpoints --
see docs/roadmap.md for that being explicitly out of scope for now).
"""

from __future__ import annotations

from .cpu import StepResult

_MODE_FORMATS = {
    "impl": lambda ob, target: "",
    "acc": lambda ob, target: "A",
    "imm": lambda ob, target: f"#${ob[0]:02X}",
    "zp": lambda ob, target: f"${ob[0]:02X}",
    "zpx": lambda ob, target: f"${ob[0]:02X},X",
    "zpy": lambda ob, target: f"${ob[0]:02X},Y",
    "abs": lambda ob, target: f"${ob[0] | (ob[1] << 8):04X}",
    "absx": lambda ob, target: f"${ob[0] | (ob[1] << 8):04X},X",
    "absy": lambda ob, target: f"${ob[0] | (ob[1] << 8):04X},Y",
    "ind": lambda ob, target: f"(${ob[0] | (ob[1] << 8):04X})",
    "indx": lambda ob, target: f"(${ob[0]:02X},X)",
    "indy": lambda ob, target: f"(${ob[0]:02X}),Y",
    "rel": lambda ob, target: f"${target:04X}",
}


def _branch_target(result: StepResult) -> int:
    if result.mode != "rel":
        return 0
    offset = result.operand_bytes[0]
    if offset >= 0x80:
        offset -= 0x100
    return (result.pc + 2 + offset) & 0xFFFF


def format_step(result: StepResult) -> str:
    hex_bytes = " ".join(f"{b:02X}" for b in (result.opcode, *result.operand_bytes))
    operand_text = _MODE_FORMATS[result.mode](result.operand_bytes, _branch_target(result))
    disasm = f"{result.mnemonic} {operand_text}".rstrip()
    return (
        f"{result.pc:04X}  {hex_bytes:<9} {disasm:<15} "
        f"A:{result.a:02X} X:{result.x:02X} Y:{result.y:02X} SP:{result.sp:02X}  "
        f"NV-BDIZC:{result.p:08b}  CYC:{result.cycles}"
    )
