"""The two-pass assembler driver: assemble(source) -> AssembledImage.

Line grammar: `[label:] [mnemonic [operand]] [;comment]`, or a `name = expr`
equate line, or a `.directive args` line (.org/.byte/.word/.res). See
docs/roadmap.md's Phase 4 plan for the full design and the "labels always
assemble as absolute addressing" rule that makes a single forward pass
over syntax (not values) enough to size every line.

Because that rule makes every line's addressing mode -- and therefore its
byte length -- knowable from syntax alone, this only needs two real
passes: one to assign addresses (walking the syntax, no symbol values
needed except already-defined equates), and one to emit bytes (now that
every symbol is known). Neither pass needs its own address-cursor replay
logic beyond the first, since pass one already recorded each emitting
line's address.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from .encoding import opcode_for
from .errors import AssemblerError
from .expr import Expr, parse_expr
from .operands import parse_operand

_LABEL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
_EQUATE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$")
_HEAD_RE = re.compile(r"^(\.?[A-Za-z_][A-Za-z0-9_]*)\s*(.*)$")

_MODE_LENGTH = {
    "impl": 1, "acc": 1,
    "imm": 2, "zp": 2, "zpx": 2, "zpy": 2, "indx": 2, "indy": 2, "rel": 2,
    "abs": 3, "absx": 3, "absy": 3, "ind": 3,
}

Item = Union[str, Expr]  # str: raw .byte string-literal content


@dataclass
class _ParsedLine:
    line_no: int
    kind: str  # "blank", "equate", "instruction", "directive"
    label: Optional[str] = None
    equate_name: Optional[str] = None
    equate_expr: Optional[Expr] = None
    mnemonic: Optional[str] = None
    mode: Optional[str] = None
    operand_expr: Optional[Expr] = None
    directive: Optional[str] = None
    items: List[Item] = field(default_factory=list)
    address: int = 0


@dataclass(frozen=True)
class AssembledImage:
    origin: int
    data: bytes


def assemble(source: str) -> AssembledImage:
    parsed_lines = [
        _parse_line(line_no, raw_line)
        for line_no, raw_line in enumerate(source.splitlines(), start=1)
    ]
    symbols: Dict[str, int] = {}
    _assign_addresses(parsed_lines, symbols)
    output = _emit(parsed_lines, symbols)
    if not output:
        raise AssemblerError("nothing to assemble -- empty program")

    origin = min(output)
    data = bytearray(max(output) - origin + 1)
    for address, byte in output.items():
        data[address - origin] = byte
    return AssembledImage(origin=origin, data=bytes(data))


# --- line parsing --------------------------------------------------------

def _strip_comment(line: str) -> str:
    in_quote: Optional[str] = None
    for i, ch in enumerate(line):
        if in_quote:
            if ch == in_quote:
                in_quote = None
        elif ch in ("'", '"'):
            in_quote = ch
        elif ch == ";":
            return line[:i]
    return line


def _split_items(text: str) -> List[str]:
    items: List[str] = []
    current: List[str] = []
    in_quote: Optional[str] = None
    for ch in text:
        if in_quote:
            current.append(ch)
            if ch == in_quote:
                in_quote = None
        elif ch in ("'", '"'):
            in_quote = ch
            current.append(ch)
        elif ch == "," and not in_quote:
            items.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    items.append("".join(current).strip())
    return items


def _parse_item(item: str) -> Item:
    if len(item) >= 2 and item[0] == '"' and item[-1] == '"':
        return item[1:-1]
    return parse_expr(item)


def _parse_line(line_no: int, raw_line: str) -> _ParsedLine:
    line = _strip_comment(raw_line).strip()
    if not line:
        return _ParsedLine(line_no=line_no, kind="blank")

    m = _EQUATE_RE.match(line)
    if m:
        name, expr_text = m.groups()
        return _ParsedLine(
            line_no=line_no, kind="equate",
            equate_name=name, equate_expr=parse_expr(expr_text),
        )

    label = None
    m = _LABEL_RE.match(line)
    if m:
        label, line = m.groups()
        line = line.strip()

    if not line:
        return _ParsedLine(line_no=line_no, kind="blank", label=label)

    m = _HEAD_RE.match(line)
    if not m:
        raise AssemblerError(f"line {line_no}: can't parse '{raw_line}'")
    head, rest = m.groups()
    rest = rest.strip()

    if head.startswith("."):
        return _parse_directive(line_no, label, head.lower(), rest)

    mnemonic = head.upper()
    try:
        mode, expr = parse_operand(mnemonic, rest)
    except AssemblerError as e:
        raise AssemblerError(f"line {line_no}: {e}") from e
    return _ParsedLine(
        line_no=line_no, kind="instruction", label=label,
        mnemonic=mnemonic, mode=mode, operand_expr=expr,
    )


def _parse_directive(line_no: int, label: Optional[str], directive: str, rest: str) -> _ParsedLine:
    if directive == ".org":
        expr = parse_expr(rest)
        if expr.is_label:
            raise AssemblerError(f"line {line_no}: .org requires a literal address")
        return _ParsedLine(line_no=line_no, kind="directive", label=label,
                            directive=directive, items=[expr])

    if directive == ".res":
        expr = parse_expr(rest)
        if expr.is_label:
            raise AssemblerError(f"line {line_no}: .res requires a literal count")
        return _ParsedLine(line_no=line_no, kind="directive", label=label,
                            directive=directive, items=[expr])

    if directive in (".byte", ".word"):
        raw_items = [i for i in _split_items(rest) if i]
        if not raw_items:
            raise AssemblerError(f"line {line_no}: {directive} needs at least one item")
        items = [_parse_item(item) for item in raw_items]
        if directive == ".word" and any(isinstance(i, str) for i in items):
            raise AssemblerError(f"line {line_no}: .word doesn't accept string literals")
        return _ParsedLine(line_no=line_no, kind="directive", label=label,
                            directive=directive, items=items)

    raise AssemblerError(f"line {line_no}: unknown directive '{directive}'")


# --- pass 1: address assignment ------------------------------------------

def _assign_addresses(parsed_lines: List[_ParsedLine], symbols: Dict[str, int]) -> None:
    address = 0
    for pl in parsed_lines:
        if pl.label is not None:
            if pl.label in symbols:
                raise AssemblerError(f"line {pl.line_no}: duplicate label '{pl.label}'")
            symbols[pl.label] = address

        if pl.kind == "equate":
            if pl.equate_name in symbols:
                raise AssemblerError(f"line {pl.line_no}: duplicate symbol '{pl.equate_name}'")
            try:
                symbols[pl.equate_name] = pl.equate_expr.evaluate(symbols)
            except AssemblerError as e:
                raise AssemblerError(
                    f"line {pl.line_no}: {e} (equates must be defined after "
                    f"whatever they depend on)"
                ) from e

        elif pl.kind == "instruction":
            pl.address = address
            address += _MODE_LENGTH[pl.mode]

        elif pl.kind == "directive":
            pl.address = address
            if pl.directive == ".org":
                address = pl.items[0].evaluate({})
            elif pl.directive == ".res":
                address += pl.items[0].evaluate({})
            elif pl.directive == ".byte":
                address += sum(len(item) if isinstance(item, str) else 1 for item in pl.items)
            elif pl.directive == ".word":
                address += 2 * len(pl.items)


# --- pass 2: byte emission -----------------------------------------------

def _emit(parsed_lines: List[_ParsedLine], symbols: Dict[str, int]) -> Dict[int, int]:
    output: Dict[int, int] = {}
    for pl in parsed_lines:
        if pl.kind == "instruction":
            _emit_instruction(pl, symbols, output)
        elif pl.kind == "directive":
            _emit_directive(pl, symbols, output)
    return output


def _emit_instruction(pl: _ParsedLine, symbols: Dict[str, int], output: Dict[int, int]) -> None:
    output[pl.address] = opcode_for(pl.mnemonic, pl.mode)
    length = _MODE_LENGTH[pl.mode]

    if length == 1:
        return

    if pl.mode == "rel":
        target = pl.operand_expr.evaluate(symbols)
        offset = target - (pl.address + 2)
        if not (-128 <= offset <= 127):
            raise AssemblerError(
                f"line {pl.line_no}: branch target ${target:04X} is out of "
                f"range (offset {offset})"
            )
        output[pl.address + 1] = offset & 0xFF
        return

    value = pl.operand_expr.evaluate(symbols)
    if length == 2:
        if not (0 <= value <= 0xFF):
            raise AssemblerError(
                f"line {pl.line_no}: operand ${value:X} doesn't fit in one byte"
            )
        output[pl.address + 1] = value
        return

    # length == 3
    if not (0 <= value <= 0xFFFF):
        raise AssemblerError(
            f"line {pl.line_no}: operand ${value:X} doesn't fit in two bytes"
        )
    output[pl.address + 1] = value & 0xFF
    output[pl.address + 2] = (value >> 8) & 0xFF


def _emit_directive(pl: _ParsedLine, symbols: Dict[str, int], output: Dict[int, int]) -> None:
    if pl.directive == ".byte":
        address = pl.address
        for item in pl.items:
            if isinstance(item, str):
                for ch in item:
                    output[address] = ord(ch) & 0xFF
                    address += 1
            else:
                value = item.evaluate(symbols)
                if not (0 <= value <= 0xFF):
                    raise AssemblerError(
                        f"line {pl.line_no}: .byte value ${value:X} doesn't fit in one byte"
                    )
                output[address] = value
                address += 1

    elif pl.directive == ".word":
        address = pl.address
        for item in pl.items:
            value = item.evaluate(symbols)
            if not (0 <= value <= 0xFFFF):
                raise AssemblerError(
                    f"line {pl.line_no}: .word value ${value:X} doesn't fit in two bytes"
                )
            output[address] = value & 0xFF
            output[address + 1] = (value >> 8) & 0xFF
            address += 2

    elif pl.directive == ".res":
        count = pl.items[0].evaluate({})
        for offset in range(count):
            output[pl.address + offset] = 0

    # ".org": nothing to emit, it only moves the address cursor.
