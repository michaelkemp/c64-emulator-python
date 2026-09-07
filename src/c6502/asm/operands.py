"""Operand syntax -> addressing mode, per docs/6502-reference.md.

Given the raw operand text following a mnemonic, determine which
addressing mode it selects and the expression (if any) naming its
address/value. See docs/roadmap.md's Phase 4 plan for the syntax table
and the "labels always assemble as absolute addressing" rule this relies
on (Expr.fits_in_byte_literal is knowable from syntax alone, so the mode
-- and therefore the instruction's byte length -- never depends on a
symbol's resolved value).
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from .encoding import ACCUMULATOR_MNEMONICS, BRANCH_MNEMONICS, has_mode
from .errors import AssemblerError
from .expr import Expr, parse_expr

_WHITESPACE_RE = re.compile(r"\s+")


def parse_operand(mnemonic: str, operand_text: str) -> Tuple[str, Optional[Expr]]:
    mode, expr = _determine_mode(mnemonic, operand_text)
    if not has_mode(mnemonic, mode):
        raise AssemblerError(
            f"{mnemonic} does not support addressing mode '{mode}' "
            f"(operand: '{operand_text}')"
        )
    return mode, expr


def _determine_mode(mnemonic: str, operand_text: str) -> Tuple[str, Optional[Expr]]:
    text = _WHITESPACE_RE.sub("", operand_text)

    if not text:
        if mnemonic in ACCUMULATOR_MNEMONICS:
            return "acc", None
        return "impl", None

    if text.upper() == "A" and mnemonic in ACCUMULATOR_MNEMONICS:
        return "acc", None

    if text.startswith("#"):
        expr = parse_expr(text[1:])
        if expr.is_label:
            raise AssemblerError(
                f"immediate operand must be a literal number/char, not a "
                f"label: '{operand_text}'"
            )
        return "imm", expr

    if text.startswith("("):
        return _parse_indirect(text)

    for suffix, zp_or_zpx_mode, abs_mode in ((",X", "zpx", "absx"), (",Y", "zpy", "absy")):
        if text.upper().endswith(suffix):
            expr = parse_expr(text[: -len(suffix)])
            return _pick_size(mnemonic, expr, zp_or_zpx_mode, abs_mode), expr

    expr = parse_expr(text)
    if mnemonic in BRANCH_MNEMONICS:
        return "rel", expr
    return _pick_size(mnemonic, expr, "zp", "abs"), expr


def _parse_indirect(text: str) -> Tuple[str, Expr]:
    upper = text.upper()
    if upper.endswith(",X)"):
        return "indx", parse_expr(text[1:-3])
    if upper.endswith("),Y"):
        return "indy", parse_expr(text[1:-3])
    if text.endswith(")"):
        return "ind", parse_expr(text[1:-1])
    raise AssemblerError(f"malformed indirect operand: '{text}'")


def _pick_size(mnemonic: str, expr: Expr, small_mode: str, large_mode: str) -> str:
    if expr.fits_in_byte_literal and has_mode(mnemonic, small_mode):
        return small_mode
    if has_mode(mnemonic, large_mode):
        return large_mode
    raise AssemblerError(
        f"{mnemonic} has no {small_mode}/{large_mode} addressing mode for this operand"
    )
