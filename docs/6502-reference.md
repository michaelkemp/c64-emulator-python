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
- We are **not** implementing the undocumented/"illegal" opcodes initially
  — the emulator should treat them as an error (loud failure) so bugs are
  visible rather than silently running as NOPs. Revisit only if a real
  program we want to run depends on them.

## Status

This file is intentionally a sketch, not the full ISA. Flesh it out further
as Phase 1 (CPU core) is implemented and specific facts need pinning down.
