#!/usr/bin/env python3
"""Boot the staged ROMs and render a PNG of the VIC-II's screen output.

Reproduces the manual check used to validate Phase 4 (see docs/vic-ii.md,
docs/roadmap.md): run the real KERNAL+BASIC unmodified through the full
CPU+Bus+CIA+VIC-II stack for a while, then render whatever's on screen.

No image library dependency (this project has none at runtime -- see
CLAUDE.md): PNG encoding here is a couple dozen lines against the
standard library's zlib, not a reason to add Pillow.

Usage:
    scripts/stage_roms.sh              # once, if you haven't already
    scripts/render_frame.py            # writes c64_boot.png
    scripts/render_frame.py --instructions 500000 --scale 3 --out boot.png
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from c64.bus import Bus  # noqa: E402
from c64.cia import CIA6526  # noqa: E402
from c64.keyboard_matrix import Cia1Ports, KeyboardMatrix  # noqa: E402
from c64.vic_ii import PALETTE, VicII  # noqa: E402
from c6502.emulator.cpu import CPU  # noqa: E402


def load_roms(roms_dir: Path) -> tuple[bytes, bytes, bytes]:
    missing = [name for name in ("kernal", "basic", "chargen") if not (roms_dir / name).exists()]
    if missing:
        raise SystemExit(
            f"Missing ROM(s) in {roms_dir}: {', '.join(missing)}. "
            "Run scripts/stage_roms.sh first."
        )
    return tuple((roms_dir / name).read_bytes() for name in ("kernal", "basic", "chargen"))


def boot_and_render(roms_dir: Path, instructions: int) -> list[list[int]]:
    kernal, basic, chargen = load_roms(roms_dir)

    keyboard = KeyboardMatrix()
    cia1 = CIA6526(port_coupler=Cia1Ports(keyboard))
    cia2 = CIA6526()
    vic = VicII()

    bus = Bus(basic_rom=basic, kernal_rom=kernal, char_rom=chargen, cia1=cia1, cia2=cia2, vic=vic)
    cpu = CPU(bus)
    cpu.reset()

    for _ in range(instructions):
        cpu.step()

    return vic.render_frame(bus)


def scale_frame(frame: list[list[int]], factor: int) -> list[list[int]]:
    if factor == 1:
        return frame
    return [
        [pixel for pixel in row for _ in range(factor)]
        for row in frame
        for _ in range(factor)
    ]


def write_png(path: Path, indexed_frame: list[list[int]], palette: list[tuple[int, int, int]]) -> None:
    height = len(indexed_frame)
    width = len(indexed_frame[0])

    raw = bytearray()
    for row in indexed_frame:
        raw.append(0)  # filter type: None
        for index in row:
            raw.extend(palette[index])

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + chunk_type
            + data
            + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        )

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB, no interlace
    idat = zlib.compress(bytes(raw))

    path.write_bytes(signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roms", type=Path, default=REPO_ROOT / "roms" / "c64")
    parser.add_argument("--instructions", type=int, default=3_000_000)
    parser.add_argument("--scale", type=int, default=2, help="nearest-neighbor pixel scale")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "c64_boot.png")
    args = parser.parse_args()

    frame = boot_and_render(args.roms, args.instructions)
    frame = scale_frame(frame, args.scale)
    write_png(args.out, frame, PALETTE)
    print(f"Wrote {args.out} ({len(frame[0])}x{len(frame)})")


if __name__ == "__main__":
    main()
