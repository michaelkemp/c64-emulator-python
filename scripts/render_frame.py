#!/usr/bin/env python3
"""Boot the staged ROMs and render a PNG of the VIC-II's screen output.

Reproduces the manual check used to validate Phase 4 (see docs/vic-ii.md,
docs/roadmap.md): run the real KERNAL+BASIC unmodified through the real
`Machine` (CPU+Bus+both CIAs+VIC-II+SID, with real interrupt delivery)
for a while, then render whatever's on screen.

**Uses `Machine`, not a hand-built CPU+Bus, deliberately**: an earlier
version of this script drove a raw `CPU`/`Bus` directly, with no CIA/
VIC-II ticking and no interrupt delivery at all. That's harmless for the
static KERNAL/BASIC boot message this script was first written to check
(printed by straight-line code before any interrupt-driven loop starts),
but produced a real, misleading black screen for a real cartridge
(Frogger) whose own screen-drawing code runs inside a raster IRQ handler
that never fired without real interrupts -- caught only by comparing
against a direct `Machine`-driven check that showed correct pixels for
the exact same address the "boot_and_render" render showed as black.

No image library dependency (this project has none at runtime -- see
CLAUDE.md): PNG encoding here is a couple dozen lines against the
standard library's zlib, not a reason to add Pillow.

Usage:
    scripts/stage_roms.sh              # once, if you haven't already
    scripts/render_frame.py            # writes c64_boot.png
    scripts/render_frame.py --instructions 500000 --scale 3 --out boot.png
    scripts/render_frame.py --cartridge cartridge-slot/some_game.crt
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from c64.cartridge import Cartridge  # noqa: E402
from c64.machine import Machine  # noqa: E402
from c64.vic_ii import PALETTE  # noqa: E402


def boot_and_render(roms_dir: Path, instructions: int, cartridge_path: Path | None = None) -> list[list[int]]:
    if not (roms_dir / "kernal").exists():
        raise SystemExit(f"No ROMs staged in {roms_dir}. Run scripts/stage_roms.sh first.")
    cartridge = Cartridge.from_file(cartridge_path) if cartridge_path is not None else None

    machine = Machine.from_roms(roms_dir, cartridge=cartridge)
    for _ in range(instructions):
        machine.step()

    return machine.vic.render_frame(machine.bus)


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
    parser.add_argument("--cartridge", type=Path, help="load this .crt file (generic/type-0 only)")
    args = parser.parse_args()

    frame = boot_and_render(args.roms, args.instructions, cartridge_path=args.cartridge)
    frame = scale_frame(frame, args.scale)
    write_png(args.out, frame, PALETTE)
    print(f"Wrote {args.out} ({len(frame[0])}x{len(frame)})")


if __name__ == "__main__":
    main()
