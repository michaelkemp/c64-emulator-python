"""Expressions: a number/char literal or a label, optionally with a
trailing +N/-N offset. Deliberately minimal -- no parens, no multi-term
arithmetic -- see docs/roadmap.md's Phase 4 plan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional

from .errors import AssemblerError

_NUMBER_RE = re.compile(r"^\$([0-9A-Fa-f]+)$|^%([01]+)$|^(-?\d+)$")
_CHAR_RE = re.compile(r"^'(.)'$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_OFFSET_RE = re.compile(r"^(.*?)\s*([+-])\s*(\d+)$")


def parse_number(text: str) -> Optional[int]:
    """Parse a bare numeric or char literal; None if `text` isn't one."""
    text = text.strip()
    m = _CHAR_RE.match(text)
    if m:
        return ord(m.group(1))
    m = _NUMBER_RE.match(text)
    if m:
        hex_digits, bin_digits, dec_digits = m.groups()
        if hex_digits is not None:
            return int(hex_digits, 16)
        if bin_digits is not None:
            return int(bin_digits, 2)
        return int(dec_digits, 10)
    return None


def is_identifier(text: str) -> bool:
    return bool(_IDENTIFIER_RE.match(text.strip()))


@dataclass(frozen=True)
class Expr:
    """A term (number/char literal, or a label name) plus an offset."""

    term: str
    is_label: bool
    offset: int = 0

    def evaluate(self, symbols: Dict[str, int]) -> int:
        if self.is_label:
            if self.term not in symbols:
                raise AssemblerError(f"undefined symbol '{self.term}'")
            return symbols[self.term] + self.offset
        value = parse_number(self.term)
        assert value is not None  # guaranteed by parse_expr
        return value + self.offset

    @property
    def fits_in_byte_literal(self) -> bool:
        """True only for a *literal* (never a label) with value 0-255 --
        this is what decides zero-page vs absolute addressing, and it must
        be knowable from syntax alone, before any symbol is resolved (see
        operands.py and the "labels always absolute" rule).
        """
        if self.is_label:
            return False
        value = parse_number(self.term)
        return value is not None and 0 <= value <= 0xFF


def parse_expr(text: str) -> Expr:
    text = text.strip()
    if not text:
        raise AssemblerError("expected an expression, found nothing")

    offset = 0
    body = text
    if parse_number(text) is None:
        m = _OFFSET_RE.match(text)
        if m:
            candidate_body, sign, digits = m.groups()
            offset = int(digits) if sign == "+" else -int(digits)
            body = candidate_body.strip()

    if parse_number(body) is not None:
        return Expr(term=body, is_label=False, offset=offset)
    if is_identifier(body):
        return Expr(term=body, is_label=True, offset=offset)
    raise AssemblerError(f"not a valid number or label: '{text}'")
