"""Loading real `.crt` cartridge images -- see docs/cartridge.md for the
register-level format, the verified memory-map interaction with
`Bus`/`CpuPort`, and known gaps.

**Only "generic" hardware type 0 cartridges are supported** (plain,
static ROM at $8000-$9FFF and/or $A000-$BFFF, no bank-switching
registers at all) -- real `.crt` files can name over 100 other hardware
types (Action Replay, Ocean type, Fun Play, System 3, various freezer
carts...), each needing its own bespoke, reverse-engineered
bank-switching register emulation. That's real, additional scope, not
attempted here -- see docs/roadmap.md's Phase 11. Anything this module
doesn't support raises `UnsupportedCartridge` with a specific reason,
never a silent guess.

Format verified against the standard reference
(ist.uwaterloo.ca/~schepers/formats/CRT.TXT) and cross-checked directly
against a real, working 16K generic cartridge image parsed by hand
before writing this -- not assumed from the spec alone.
"""

from __future__ import annotations

import struct
from pathlib import Path

CRT_MAGIC = b"C64 CARTRIDGE   "
CHIP_MAGIC = b"CHIP"

GENERIC_HARDWARE_TYPE = 0

BANK_SIZE = 0x2000  # 8KB -- one bank's worth of ROML or ROMH
ROML_ADDRESS = 0x8000
ROMH_ADDRESS = 0xA000

CHIP_TYPE_ROM = 0


class UnsupportedCartridge(Exception):
    """A real, named limitation (unsupported hardware type, bank
    switching, chip type, or size) -- never guessed at or silently
    truncated. See docs/cartridge.md."""


class Cartridge:
    """A parsed generic (type 0) cartridge image: at most one 8KB ROML
    bank ($8000-$9FFF) and one 8KB ROMH bank ($A000-$BFFF), plus the
    real EXROM/GAME line states the real header specifies -- `Bus` reads
    these exactly the way the real 6510/PLA's address decode does (see
    docs/cartridge.md for the verified truth table). `exrom`/`game` are
    the *raw* line values from the file (0 = pulled low/asserted, 1 =
    high/inactive) -- deliberately not inverted to an "active" boolean,
    to match how every real reference (the CRT spec, VICE's own source,
    the C64 PLA documentation) writes these tables, avoiding a
    silent double-negation bug.
    """

    def __init__(
        self,
        *,
        name: str,
        exrom: int,
        game: int,
        rom_lo: bytes | None,
        rom_hi: bytes | None,
    ) -> None:
        self.name = name
        self.exrom = exrom
        self.game = game
        self.rom_lo = rom_lo
        self.rom_hi = rom_hi

    @classmethod
    def from_file(cls, path: Path | str) -> "Cartridge":
        path = Path(path)
        data = path.read_bytes()

        if data[0:16] != CRT_MAGIC:
            raise UnsupportedCartridge(f"{path}: not a .crt file (missing '{CRT_MAGIC.decode()}' signature)")
        if len(data) < 0x40:
            raise UnsupportedCartridge(f"{path}: file too short to hold a full 64-byte header")

        header_len = struct.unpack(">I", data[0x10:0x14])[0]
        hardware_type = struct.unpack(">H", data[0x16:0x18])[0]
        exrom = data[0x18]
        game = data[0x19]
        name = data[0x20:0x40].rstrip(b"\x00").decode("ascii", errors="replace")

        if hardware_type != GENERIC_HARDWARE_TYPE:
            raise UnsupportedCartridge(
                f"{path}: hardware type {hardware_type} needs its own bank-switching "
                "register emulation -- only generic type 0 (static ROM, no bank "
                "switching) is supported. See docs/cartridge.md."
            )
        if exrom == 1 and game == 0:
            raise UnsupportedCartridge(
                f"{path}: Ultimax mode (EXROM=1, GAME=0) isn't supported yet -- it "
                "maps ROM into $E000-$FFFF and disables most RAM, unlike the plain "
                "8K/16K cases this module handles. See docs/cartridge.md."
            )
        if exrom == 1 and game == 1:
            raise UnsupportedCartridge(f"{path}: EXROM=1, GAME=1 means no cartridge is present at all")

        rom_lo: bytes | None = None
        rom_hi: bytes | None = None
        offset = header_len
        while offset < len(data):
            if data[offset : offset + 4] != CHIP_MAGIC:
                raise UnsupportedCartridge(f"{path}: expected a CHIP packet at offset {offset}, found something else")
            pkt_len = struct.unpack(">I", data[offset + 4 : offset + 8])[0]
            chip_type = struct.unpack(">H", data[offset + 8 : offset + 10])[0]
            bank = struct.unpack(">H", data[offset + 10 : offset + 12])[0]
            load_addr = struct.unpack(">H", data[offset + 12 : offset + 14])[0]
            img_size = struct.unpack(">H", data[offset + 14 : offset + 16])[0]
            rom_data = bytes(data[offset + 16 : offset + 16 + img_size])

            if chip_type != CHIP_TYPE_ROM:
                raise UnsupportedCartridge(
                    f"{path}: CHIP packet has chip_type={chip_type} (RAM/Flash) -- "
                    "only plain ROM (0) is supported"
                )
            if bank != 0:
                raise UnsupportedCartridge(
                    f"{path}: CHIP packet targets bank {bank} -- bank-switched "
                    "cartridges aren't supported, only single-bank generic ones"
                )

            if load_addr == ROML_ADDRESS and img_size == BANK_SIZE * 2:
                rom_lo, rom_hi = rom_data[:BANK_SIZE], rom_data[BANK_SIZE:]
            elif load_addr == ROML_ADDRESS and img_size == BANK_SIZE:
                rom_lo = rom_data
            elif load_addr == ROMH_ADDRESS and img_size == BANK_SIZE:
                rom_hi = rom_data
            else:
                raise UnsupportedCartridge(
                    f"{path}: CHIP packet at load address {load_addr:#06x} size "
                    f"{img_size:#06x} doesn't match a supported ROML/ROMH layout"
                )

            offset += pkt_len

        return cls(name=name, exrom=exrom, game=game, rom_lo=rom_lo, rom_hi=rom_hi)
