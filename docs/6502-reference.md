# 6502 reference notes

Condensed notes we author ourselves, for quick recall while implementing the
emulator. For the authoritative opcode-by-opcode tables (cycle counts, full
addressing-mode matrix per instruction), use the external references below
rather than duplicating them here — they're actively maintained and easy to
get subtly wrong by hand-copying.

- Full instruction set reference: https://masswerk.at/6502/6502_instruction_set.html
- General 6502 knowledge base / datasheets / forum: https://6502.org

## Registers

| Register | Width | Purpose |
|---|---|---|
| A | 8-bit | Accumulator |
| X | 8-bit | Index register |
| Y | 8-bit | Index register |
| SP | 8-bit | Stack pointer (stack lives at `$0100`–`$01FF`, grows downward) |
| PC | 16-bit | Program counter |
| P | 8-bit | Status/flags register |

## Status flags (P register)

| Bit | Flag | Meaning |
|---|---|---|
| 7 | N | Negative — set to bit 7 of the result |
| 6 | V | Overflow — signed arithmetic overflow |
| 5 | - | Unused, always reads as 1 |
| 4 | B | Break — set when P is pushed by `BRK`/`PHP`, not a real stored flag |
| 3 | D | Decimal mode — BCD arithmetic for `ADC`/`SBC` when set |
| 2 | I | Interrupt disable — blocks IRQ (not NMI) when set |
| 1 | Z | Zero — set when the result is zero |
| 0 | C | Carry |

Note: bit 5 and the "B flag" are not real bits of the physical status
register — they only appear in the byte value produced when P is pushed to
the stack. This distinction matters for getting `PHP`/`PLP`/`BRK`/interrupt
behavior bit-exact; see the functional test suite for coverage of this.

## Addressing modes

Implied, Accumulator, Immediate (`#$nn`), Zero Page, Zero Page,X, Zero
Page,Y, Absolute, Absolute,X, Absolute,Y, Indirect (`JMP` only, and famously
buggy on page boundaries on NMOS — must reproduce the bug), Indexed Indirect
`(zp,X)`, Indirect Indexed `(zp),Y`, Relative (branches).

## Vectors

| Vector | Address |
|---|---|
| NMI | `$FFFA`/`$FFFB` |
| RESET | `$FFFC`/`$FFFD` |
| IRQ/BRK | `$FFFE`/`$FFFF` |

## Known NMOS quirks to reproduce faithfully

- `JMP (indirect)` does not correctly cross a page boundary: if the pointer
  is at `$xxFF`, the high byte is fetched from `$xx00` of the *same* page,
  not `$(xx+1)00`. This bug is famous enough that a correct emulator must
  reproduce it, not "fix" it, unless we later add an explicit 65C02 mode.
  Confirm exact behavior against masswerk.at and Klaus Dormann's test suite
  before implementing.
- Decimal mode (`D` flag) affects `ADC`/`SBC` only, and NMOS decimal-mode
  flag behavior for N/V/Z is itself quirky — verify against the dedicated
  `6502_decimal_test` in Klaus Dormann's suite rather than trusting
  intuition.
## Illegal/undocumented opcodes

Originally deliberately unimplemented (treated as a loud `IllegalOpcodeError`
failure) — revisited once it became clear real C64 software (not just
synthetic test cases) genuinely depends on them: undocumented opcodes were
routinely used deliberately in copy-protected commercial games and demoscene
code, both for code density and as an anti-disassembly/anti-emulation trick
that assumes a naive tool won't handle them.

Of the 256 possible opcode byte values, 105 are undocumented. They split into
four groups by how well-defined their real-hardware behavior is; this
project implements the first three (97 opcodes) and deliberately still does
not implement the fourth (8 opcodes):

1. **Reliable combined ops (57)** — deterministic fusions of two documented
   instructions sharing one memory read: `LAX` (LDA+LDX), `SAX` (store
   A AND X), `DCP` (DEC+CMP), `ISC`/`ISB` (INC+SBC), `SLO` (ASL+ORA), `RLA`
   (ROL+AND), `SRE` (LSR+EOR), `RRA` (ROR+ADC — the ROR's carry-out feeds the
   ADC's carry-in, same as real hardware), plus the immediate-only `ANC`,
   `ALR`/`ASR`, `ARR`, `SBX`/`AXS`. `$EB` (`USBC`) is a plain second encoding
   of legal `SBC`. **Implemented** in `src/c6502/emulator/instructions.py`.
   `ARR`'s widely-documented binary-mode C/V-from-bits-6/5 formula is
   implemented; its additional decimal-mode-dependent flag wrinkle (in the
   same spirit as `ADC`/`SBC`'s own quirky decimal flags, above) is **not**
   — a disclosed gap, since decimal-mode `ARR` is vanishingly rare in real
   C64 software.
2. **Multi-byte/multi-cycle NOPs (27)** — read-and-discard, at various
   addressing modes/operand sizes/cycle counts (including page-cross timing
   identical to their legal counterparts). Behaviorally identical to the
   legal NOP; **implemented** by reusing `instr.nop` under new opcode-table
   entries.
3. **`JAM`/`KIL`/`HLT` (12: `$02,$12,$22,$32,$42,$52,$62,$72,$92,$B2,$D2,$F2`)**
   — not "does something," a genuine dead end: real hardware locks the CPU
   in an internal fetch cycle indefinitely, recoverable only by a reset.
   **Implemented** as a distinct `ProcessorJammed` exception (not folded into
   `IllegalOpcodeError`, since this is real documented behavior, not
   something unimplemented) — see `src/c6502/emulator/cpu.py`.
4. **Chip-unstable ops (8, still unimplemented)** — `ANE`/`XAA` (`$8B`),
   `LXA` (`$AB`), `LAS`/`LAR` (`$BB`), `SHA`/`AHX` (`$9F`, `$93`), `SHX`
   (`$9E`), `SHY` (`$9C`), `TAS`/`SHS` (`$9B`). Real chip-to-chip behavior
   genuinely varies with analog bus conditions/chip series — even the
   community reverse-engineering references disagree on exact semantics.
   Still raise `IllegalOpcodeError`; revisit only if a specific real program
   depends on one and its exact needed behavior can be pinned down.

Sources consulted for exact opcode bytes, addressing modes, cycle counts,
and flag semantics (read for understanding; nothing vendored, same license
discipline as `docs/testing-strategy.md`'s SID/reSID rule):
[masswerk.at's undocumented opcode tables](https://www.masswerk.at/6502/6502_instruction_set.html)
and
[masswerk.at's "6502 Illegal Opcodes Demystified"](https://www.masswerk.at/nowgobang/2021/6502-illegal-opcodes).

A verified-license test ROM specific to illegal-opcode correctness (the kind
of thing Klaus Dormann's suite deliberately doesn't cover — confirmed: its
own "extended" test in the same repository tests the *65C02's* undefined
opcodes, a different chip with different undefined-opcode behavior, not
NMOS/6510) was evaluated and not found: the classic community reference
(Wolfgang Lorenz's test suite / `AllSuiteA`) is only ever described as
"believed to be public domain" with no primary source establishing that —
exactly the kind of unverified claim `docs/testing-strategy.md`'s license
discipline rule exists to catch (cf. the ROM licensing lesson in the main
`CLAUDE.md`). Correctness here is instead established the same way the rest
of this project's own hand-assembled tests are: `tests/emulator/
test_illegal_opcodes.py` verifies each implemented instruction's semantics
against hand-computed expected values, not a fetched suite.

## Status

This file is intentionally a sketch, not the full ISA. Flesh it out further
as Phase 1 (CPU core) is implemented and specific facts need pinning down.
