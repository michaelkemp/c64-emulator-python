#!/usr/bin/env python3
"""Wrap one or two raw, headerless ROM chip dumps into a proper .crt
container this project's `Cartridge.from_file()` can load.

Some real cartridge dumps circulate as raw chip images with no container
at all -- e.g. Simon's BASIC as two separate 8K files (one per chip, at
$8000 and $A000), or a diagnostic cartridge whose EPROM turned out to
pack multiple independent 16K cartridge images back-to-back in one
bigger file (see docs/cartridge.md's Usage section). Building the ~80-
byte .crt container by hand for these is simpler and more honest than
hunting online for a pre-made .crt -- this project never fetches ROM/
cartridge content itself (see CLAUDE.md's ROM-licensing lesson); you
already have the dump, this just wraps it in the format
`src/c64/cartridge.py` already parses.

Only builds what this project supports: generic/type-0 (plain ROM at
$8000-$9FFF and/or $A000-$BFFF, EXROM=0/GAME=0, no bank-switching) --
the same shape as the real Galaxian/Frogger .crt files already in
cartridge-slot/. Round-trips the written file through this project's
own Cartridge.from_file() before declaring success, so a malformed
header is caught immediately, not discovered later via run_c64.py's
"Not loading ...: <reason>".

Pass --ultimax for Ultimax-mode cartridges (EXROM=1/GAME=0) -- ROMH
then loads at $E000 instead of $A000, replacing the KERNAL. See
docs/cartridge.md's Ultimax section for the real memory-map
consequences (verified against VICE's own source).

Usage:
    # Two separate 8K chip files (e.g. Simon's BASIC)
    scripts/wrap_raw_cartridge.py \\
        --chip 0x8000:C64108_Simons_Basic_1-8000.bin \\
        --chip 0xA000:C64108_Simons_Basic_2-a000.bin \\
        --name "SIMONS BASIC" --out cartridge-slot/simons_basic.crt

    # A 16K slice extracted from a bigger dump (e.g. a diagnostic
    # cartridge's EPROM holding multiple independent images back-to-back)
    scripts/wrap_raw_cartridge.py \\
        --chip 0x8000:diag.bin:0x0000:0x4000 \\
        --name "DEAD TEST" --out cartridge-slot/dead_test.crt

    # An Ultimax-mode 8K ROM meant to load at $E000
    scripts/wrap_raw_cartridge.py --ultimax \\
        --chip 0xE000:destest-max.rom \\
        --name "DESTESTMAX" --out cartridge-slot/destest_max.crt
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from c64.cartridge import Cartridge, UnsupportedCartridge  # noqa: E402

CRT_MAGIC = b"C64 CARTRIDGE   "
CHIP_MAGIC = b"CHIP"
HEADER_LEN = 0x40
CHIP_HEADER_LEN = 16
BANK_SIZE = 0x2000
ROML_ADDRESS = 0x8000
ROMH_ADDRESS = 0xA000
ULTIMAX_ROMH_ADDRESS = 0xE000


def parse_chip_arg(spec: str) -> tuple[int, bytes]:
    """'ADDR:PATH' (whole file is this chip's data) or
    'ADDR:PATH:OFFSET:LENGTH' (a slice of a bigger dump) -> (load_address, data)."""
    parts = spec.split(":")
    if len(parts) not in (2, 4):
        raise SystemExit(f"--chip must be ADDR:PATH or ADDR:PATH:OFFSET:LENGTH, got {spec!r}")
    addr = int(parts[0], 0)
    path = Path(parts[1])
    raw = path.read_bytes()
    if len(parts) == 4:
        offset = int(parts[2], 0)
        length = int(parts[3], 0)
        if offset + length > len(raw):
            raise SystemExit(
                f"{path}: requested [{offset:#x}:{offset + length:#x}) but file is only {len(raw):#x} bytes"
            )
        data = raw[offset : offset + length]
    else:
        data = raw
    return addr, data


def build_chip_packet(load_address: int, data: bytes) -> bytes:
    packet_len = CHIP_HEADER_LEN + len(data)
    return (
        CHIP_MAGIC
        + struct.pack(">I", packet_len)
        + struct.pack(">HHHH", 0, 0, load_address, len(data))  # chip_type=ROM, bank=0
        + data
    )


def build_crt(name: str, chips: list[tuple[int, bytes]], ultimax: bool = False) -> bytes:
    header = bytearray(HEADER_LEN)
    header[0x00:0x10] = CRT_MAGIC
    header[0x10:0x14] = struct.pack(">I", HEADER_LEN)
    header[0x14:0x16] = struct.pack(">H", 0x0100)  # cartridge version 1.0
    header[0x16:0x18] = struct.pack(">H", 0)  # hardware type 0 (generic)
    header[0x18] = 1 if ultimax else 0  # EXROM
    header[0x19] = 0  # GAME=0 either way -- 0/0 is the standard ROM-present config, 1/0 is Ultimax
    header[0x20:0x40] = name.encode("ascii", errors="replace")[:32].ljust(32, b"\x00")

    body = b"".join(build_chip_packet(addr, data) for addr, data in chips)
    return bytes(header) + body


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--chip", action="append", required=True, metavar="ADDR:PATH[:OFFSET:LENGTH]",
        help="one ROM chip's load address ($8000 or $A000) and source bytes; "
        "pass twice for a two-chip 8K+8K cartridge",
    )
    parser.add_argument("--name", default="", help="cartridge name stored in the header (up to 32 ASCII chars)")
    parser.add_argument(
        "--ultimax", action="store_true",
        help="build an Ultimax-mode header (EXROM=1/GAME=0) -- ROMH then loads at $E000, not $A000",
    )
    parser.add_argument("--out", type=Path, required=True, help="output .crt path")
    args = parser.parse_args()

    if len(args.chip) > 2:
        raise SystemExit("at most two --chip args are supported (ROML at $8000, ROMH at $A000/$E000)")

    romh_address = ULTIMAX_ROMH_ADDRESS if args.ultimax else ROMH_ADDRESS
    chips = [parse_chip_arg(spec) for spec in args.chip]
    seen_addresses = set()
    for addr, data in chips:
        if addr == ROML_ADDRESS and len(data) not in (BANK_SIZE, BANK_SIZE * 2):
            raise SystemExit(f"chip at $8000 must be {BANK_SIZE:#x} or {BANK_SIZE * 2:#x} bytes, got {len(data):#x}")
        elif addr == romh_address and len(data) != BANK_SIZE:
            raise SystemExit(f"chip at {romh_address:#06x} must be {BANK_SIZE:#x} bytes, got {len(data):#x}")
        elif addr not in (ROML_ADDRESS, romh_address):
            raise SystemExit(f"chip load address must be $8000 or {romh_address:#06x}, got {addr:#x}")
        if addr in seen_addresses:
            raise SystemExit(f"two --chip args both target {addr:#x}")
        seen_addresses.add(addr)

    crt_bytes = build_crt(args.name, chips, ultimax=args.ultimax)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(crt_bytes)

    try:
        cart = Cartridge.from_file(args.out)
    except UnsupportedCartridge as exc:
        raise SystemExit(f"wrote {args.out} but this project's own parser rejects it: {exc}")

    print(
        f"Wrote {args.out} ({len(crt_bytes)} bytes) -- parsed back as: "
        f"name={cart.name!r} rom_lo={'yes' if cart.rom_lo else 'no'} rom_hi={'yes' if cart.rom_hi else 'no'}"
    )


if __name__ == "__main__":
    main()
