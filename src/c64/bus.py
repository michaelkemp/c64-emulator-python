"""The real C64 memory map: RAM, bank-switched ROM, and I/O windows.

Unlike `c6502.emulator.bus.FlatMemory` (a flat 64KB block used to test the
CPU core in isolation), the real C64 has RAM *everywhere* in its 64KB
address space, with BASIC ROM, KERNAL ROM, character ROM, and the
VIC-II/SID/CIA/color-RAM registers overlaid on top of specific windows,
switched in and out by the 6510's I/O port at $00/$01 (see `cpu_port.py`).
Writes to a ROM-overlaid address still land in the RAM underneath (real
software relies on this -- e.g. copying the KERNAL into RAM to patch it);
only reads see the overlay. The one exception is the I/O window
($D000-$DFFF when CHAREN selects I/O rather than character ROM): the I/O
chips replace the underlying RAM entirely there, for both reads and
writes, while I/O is selected.

Bank-switching table (LORAM/HIRAM/CHAREN from `CpuPort`), from the C64
Programmer's Reference Guide's memory map appendix -- this is the
non-cartridge case:

    LORAM HIRAM CHAREN | $A000-$BFFF | $D000-$DFFF | $E000-$FFFF
      1     1     1    | BASIC ROM   | I/O         | KERNAL ROM   (default)
      1     1     0    | BASIC ROM   | Char ROM    | KERNAL ROM
      0     1     1    | RAM         | I/O         | KERNAL ROM
      0     1     0    | RAM         | Char ROM    | KERNAL ROM
      1     0     1    | RAM         | I/O         | RAM
      1     0     0    | RAM         | Char ROM    | RAM
      0     0     1    | RAM         | I/O         | RAM
      0     0     0    | RAM         | Char ROM    | RAM

Which reduces to: BASIC ROM needs LORAM *and* HIRAM; KERNAL ROM needs only
HIRAM; $D000-$DFFF depends only on CHAREN (I/O when set, character ROM
when clear) -- never plain RAM, regardless of LORAM/HIRAM.

**Cartridges** (`c64.cartridge.Cartridge`, generic/type-0 only -- see
docs/cartridge.md) add EXROM/GAME to the same PLA, at $8000-$9FFF
(ROML) and $A000-$BFFF (ROMH, 16K mode only). Verified against VICE's
own `c64meminit.c` source directly (not a summarized secondary source --
a first web summary of a wiki table gave an internally-contradictory
answer for this exact question, only real emulator source settled it):

    GAME EXROM LORAM HIRAM | $8000-$9FFF | $A000-$BFFF
      1    0     1     1   | ROML        | BASIC ROM     (8K cart)
      0    0     1     1   | ROML        | ROMH          (16K cart)
      0    0     0     1   | RAM         | ROMH          (16K cart)
      *    *     0     *   | RAM         | RAM/BASIC per table above (ROML needs LORAM *and* HIRAM)

Which reduces to: ROML needs EXROM inactive (0) *and* LORAM *and* HIRAM
(unlike ROMH, LORAM matters here -- confirmed directly from VICE's
`c64meminit_roml_config`, not assumed); ROMH (16K mode only, GAME and
EXROM both 0) needs only HIRAM, independent of LORAM. Ultimax mode
(GAME=0, EXROM=1 -- ROMH forced into $E000-$FFFF instead, most RAM
disabled) isn't modeled; `Cartridge.from_file` refuses to load one
rather than silently getting it wrong.

The VIC-II, SID, and the two CIAs don't exist yet (Phases 3/4/6 in
docs/roadmap.md) -- their register windows are wired up as optional
constructor arguments (any object with `read_register(offset)` /
`write_register(offset, value)`); left as `None`, those windows read as
open bus (`0xFF`) and ignore writes, so this Bus is fully testable on its
own before any chip exists. Color RAM is real, always-present 4-bit-wide
SRAM (not a chip register), so it's modeled directly here instead of
waiting for a chip: only the low nibble is stored, and reads return it
with the high nibble forced to 1s -- real hardware's high nibble is
undriven/noisy, and this is the common simplification other emulators use
too.

ROM images (`basic_rom`/`kernal_rom`/`char_rom`) are optional. Without
one, that ROM's window just falls through to RAM -- useful for testing
the bank-switching logic itself without needing real Commodore ROM
images (see docs/roadmap.md's Phase 1 for why those are never vendored
here; `scripts/stage_roms.sh` stages the user's own local copies into the
gitignored `roms/c64/`, which this class does not read from directly).
"""

from __future__ import annotations

from typing import Protocol

from c64.cartridge import Cartridge
from c64.cpu_port import CpuPort

RAM_SIZE = 0x10000

BASIC_ROM_START = 0xA000
BASIC_ROM_SIZE = 0x2000
KERNAL_ROM_START = 0xE000
KERNAL_ROM_SIZE = 0x2000
CHAR_ROM_START = 0xD000
CHAR_ROM_SIZE = 0x1000

CART_ROML_START = 0x8000
CART_ROML_SIZE = 0x2000
CART_ROMH_START = 0xA000
CART_ROMH_SIZE = 0x2000

IO_START = 0xD000
IO_END = 0xDFFF
VIC_START, VIC_END, VIC_WINDOW = 0xD000, 0xD3FF, 0x40
SID_START, SID_END, SID_WINDOW = 0xD400, 0xD7FF, 0x20
COLOR_RAM_START, COLOR_RAM_END = 0xD800, 0xDBFF
CIA1_START, CIA1_END, CIA_WINDOW = 0xDC00, 0xDCFF, 0x10
CIA2_START, CIA2_END = 0xDD00, 0xDDFF


class RegisterChip(Protocol):
    """What `Bus` needs from a VIC-II/SID/CIA once one exists."""

    def read_register(self, offset: int) -> int: ...

    def write_register(self, offset: int, value: int) -> None: ...


class Bus:
    """The C64's bank-switched memory map, implementing the CPU's bus interface."""

    def __init__(
        self,
        *,
        basic_rom: bytes | None = None,
        kernal_rom: bytes | None = None,
        char_rom: bytes | None = None,
        cartridge: Cartridge | None = None,
        vic: RegisterChip | None = None,
        sid: RegisterChip | None = None,
        cia1: RegisterChip | None = None,
        cia2: RegisterChip | None = None,
    ) -> None:
        _check_rom_size("basic_rom", basic_rom, BASIC_ROM_SIZE)
        _check_rom_size("kernal_rom", kernal_rom, KERNAL_ROM_SIZE)
        _check_rom_size("char_rom", char_rom, CHAR_ROM_SIZE)
        _check_rom_size("cartridge.rom_lo", cartridge.rom_lo if cartridge else None, CART_ROML_SIZE)
        _check_rom_size("cartridge.rom_hi", cartridge.rom_hi if cartridge else None, CART_ROMH_SIZE)

        self.port = CpuPort()
        self.basic_rom = basic_rom
        self.kernal_rom = kernal_rom
        self.char_rom = char_rom
        # Raw EXROM/GAME line values (0=asserted/low, 1=inactive/high) --
        # 1/1 is the real, pulled-up "no cartridge" state, matching the
        # default when `cartridge` is None. See this module's docstring
        # for the verified truth table and docs/cartridge.md.
        self.cart_exrom = cartridge.exrom if cartridge is not None else 1
        self.cart_game = cartridge.game if cartridge is not None else 1
        self.cart_rom_lo = cartridge.rom_lo if cartridge is not None else None
        self.cart_rom_hi = cartridge.rom_hi if cartridge is not None else None
        self.vic = vic
        self.sid = sid
        self.cia1 = cia1
        self.cia2 = cia2

        self._ram = bytearray(RAM_SIZE)
        self._color_ram = bytearray(COLOR_RAM_END - COLOR_RAM_START + 1)

    def read8(self, address: int) -> int:
        address &= 0xFFFF
        if address == 0x0000:
            return self.port.read_ddr()
        if address == 0x0001:
            return self.port.read_data()
        if (
            CART_ROML_START <= address < CART_ROML_START + CART_ROML_SIZE
            and self.cart_exrom == 0
            and self.port.loram
            and self.port.hiram
            and self.cart_rom_lo is not None
        ):
            return self.cart_rom_lo[address - CART_ROML_START]
        if (
            CART_ROMH_START <= address < CART_ROMH_START + CART_ROMH_SIZE
            and self.cart_game == 0
            and self.cart_exrom == 0
            and self.port.hiram
            and self.cart_rom_hi is not None
        ):
            return self.cart_rom_hi[address - CART_ROMH_START]
        if (
            BASIC_ROM_START <= address < BASIC_ROM_START + BASIC_ROM_SIZE
            and self.port.loram
            and self.port.hiram
            and self.basic_rom is not None
        ):
            return self.basic_rom[address - BASIC_ROM_START]
        if IO_START <= address <= IO_END:
            return self._read_io_window(address)
        if (
            KERNAL_ROM_START <= address
            and self.port.hiram
            and self.kernal_rom is not None
        ):
            return self.kernal_rom[address - KERNAL_ROM_START]
        return self._ram[address]

    def write8(self, address: int, value: int) -> None:
        address &= 0xFFFF
        value &= 0xFF
        if address == 0x0000:
            self.port.write_ddr(value)
            return
        if address == 0x0001:
            self.port.write_data(value)
            return
        if IO_START <= address <= IO_END and self.port.charen:
            self._write_io_window(address, value)
            return
        self._ram[address] = value

    def read16(self, address: int) -> int:
        lo = self.read8(address)
        hi = self.read8(address + 1)
        return lo | (hi << 8)

    def write16(self, address: int, value: int) -> None:
        self.write8(address, value & 0xFF)
        self.write8(address + 1, (value >> 8) & 0xFF)

    def load(self, address: int, data: bytes) -> None:
        for offset, byte in enumerate(data):
            self.write8(address + offset, byte)

    def vic_bank_base(self) -> int:
        """The base address of the 16KB window the VIC-II currently sees,
        selected by CIA2 port A bits 0-1 -- see docs/vic-ii.md for the
        (inverted) encoding. Defaults to bank 0 if no CIA2 is attached,
        matching a detached port's own all-1s reset state."""
        bits = self.cia2.read_register(0) & 0x03 if self.cia2 is not None else 0x03
        return (3 - bits) * 0x4000

    def read_vic(self, address: int) -> int:
        """How the VIC-II sees memory: relative to its own 16KB bank, not
        the CPU's LORAM/HIRAM/CHAREN view -- with character ROM hardwired
        into view whenever that lands on $1000-$1FFF of banks 0 or 2, per
        docs/vic-ii.md."""
        offset = address & 0x3FFF
        bank_base = self.vic_bank_base()
        if bank_base in (0x0000, 0x8000) and 0x1000 <= offset <= 0x1FFF and self.char_rom is not None:
            return self.char_rom[offset - 0x1000]
        return self._ram[(bank_base + offset) & 0xFFFF]

    def read_color_nibble(self, index: int) -> int:
        """Color RAM, as the VIC-II sees it directly (not bank-switched)."""
        return self._color_ram[index & (len(self._color_ram) - 1)]

    def _read_io_window(self, address: int) -> int:
        if not self.port.charen:
            if self.char_rom is not None:
                return self.char_rom[address - CHAR_ROM_START]
            return self._ram[address]
        if VIC_START <= address <= VIC_END:
            return _read_chip(self.vic, address - VIC_START, VIC_WINDOW)
        if SID_START <= address <= SID_END:
            return _read_chip(self.sid, address - SID_START, SID_WINDOW)
        if COLOR_RAM_START <= address <= COLOR_RAM_END:
            return 0xF0 | self._color_ram[address - COLOR_RAM_START]
        if CIA1_START <= address <= CIA1_END:
            return _read_chip(self.cia1, address - CIA1_START, CIA_WINDOW)
        if CIA2_START <= address <= CIA2_END:
            return _read_chip(self.cia2, address - CIA2_START, CIA_WINDOW)
        return 0xFF  # cartridge I/O1 ($DE00-DEFF) / I/O2 ($DF00-DFFF): open bus

    def _write_io_window(self, address: int, value: int) -> None:
        if VIC_START <= address <= VIC_END:
            _write_chip(self.vic, address - VIC_START, VIC_WINDOW, value)
        elif SID_START <= address <= SID_END:
            _write_chip(self.sid, address - SID_START, SID_WINDOW, value)
        elif COLOR_RAM_START <= address <= COLOR_RAM_END:
            self._color_ram[address - COLOR_RAM_START] = value & 0x0F
        elif CIA1_START <= address <= CIA1_END:
            _write_chip(self.cia1, address - CIA1_START, CIA_WINDOW, value)
        elif CIA2_START <= address <= CIA2_END:
            _write_chip(self.cia2, address - CIA2_START, CIA_WINDOW, value)
        # else: cartridge I/O1/I/O2 -- no cartridge support, write ignored


def _check_rom_size(name: str, rom: bytes | None, expected_size: int) -> None:
    if rom is not None and len(rom) != expected_size:
        raise ValueError(f"{name} must be exactly {expected_size} bytes, got {len(rom)}")


def _read_chip(chip: RegisterChip | None, offset: int, window: int) -> int:
    if chip is None:
        return 0xFF
    return chip.read_register(offset % window)


def _write_chip(chip: RegisterChip | None, offset: int, window: int, value: int) -> None:
    if chip is not None:
        chip.write_register(offset % window, value)
