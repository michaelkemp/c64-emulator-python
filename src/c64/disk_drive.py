"""KERNAL-trap disk emulation (strategy 1 -- see docs/disk.md for why not
full 1541 drive emulation yet, and the full verified trap protocol this
implements).

Traps LOAD ($FFD5) and SAVE ($FFD8) at their fixed, revision-stable
KERNAL jump-table addresses, for device numbers 8+ only -- device 0
(keyboard) and 1 (cassette) always fall through to the real, unmodified
KERNAL routine (this class's `maybe_intercept` just returns False, and
`Machine.step()` calls `cpu.step()` normally). Everything before the
trap (BASIC tokenizing LOAD/SAVE, calling SETNAM/SETLFS) and after it
(BASIC's own post-LOAD relinking of its program-end pointers, driven by
the X/Y this trap returns exactly as a real load would) is genuine,
unmodified KERNAL/BASIC ROM code -- only the "transfer bytes over a
serial bus to/from a real spinning disk" part is replaced.

Disclosed simplification: a trapped LOAD/SAVE consumes zero emulated CPU
cycles (Machine.step() returns 0 for that step) -- strategy 1 doesn't
model real disk I/O transfer time at all, unlike the genuine (slow)
serial-bus transfer a real drive takes. See docs/disk.md.
"""

from __future__ import annotations

from c64.d64 import D64Image, DiskFullError, FileExistsOnDisk, FileNotFoundOnDisk

LOAD_VECTOR = 0xFFD5
SAVE_VECTOR = 0xFFD8

FILENAME_LEN_ZP = 0xB7
LOGICAL_FILE_ZP = 0xB8
SECONDARY_ADDR_ZP = 0xB9
DEVICE_ZP = 0xBA
FILENAME_PTR_LO_ZP = 0xBB
FILENAME_PTR_HI_ZP = 0xBC

# KERNAL status code returned in A when Carry is set on error -- verified
# against the real KERNAL error table (sta.c64.org/cbm64krnerr.html),
# which only defines codes 1-9. "FILE EXISTS" and "DISK FULL" are NOT in
# that table -- they're disk-error-channel-only conditions (see
# _handle_save), so there's no code for them here at all, deliberately.
# "DEVICE NOT PRESENT" (5) is real too, but this module never needs to
# raise it itself -- an unmounted device just falls through to the real,
# unmodified KERNAL, which already produces that error correctly on its
# own (verified: tests/c64/test_disk_drive.py's unmounted-device test).
ERR_FILE_NOT_FOUND = 4

FIRST_VALID_DEVICE = 8

# Real drives declare the directory-listing "file"'s load address as
# $0401 regardless of host machine (shared DOS code across the PET/VIC-20/
# C64 family, where only the C64 actually starts BASIC at $0801) -- and
# every line's next-line pointer is left as this same placeholder rather
# than a real chained address, since the drive doesn't know where its
# raw bytes will actually land once loaded. Real, unmodified C64 BASIC
# detects a "$" load specially and re-chains the pointers correctly
# after the fact (see docs/disk.md) -- this project doesn't reimplement
# that fixup itself, it relies on the genuine ROM already doing it,
# exactly matching what a real drive's raw output looks like.
DIRECTORY_LOAD_ADDRESS = 0x0401
DIRECTORY_LINK_PLACEHOLDER = 0x0101


class DiskDrives:
    """Zero or more mounted `D64Image`s, addressed by device number (8,
    9, ... -- real 1541s are jumper-configurable the same way)."""

    def __init__(self) -> None:
        self.images: dict[int, D64Image] = {}

    def mount(self, device: int, image: D64Image) -> None:
        self.images[device] = image

    def unmount(self, device: int) -> None:
        self.images.pop(device, None)

    def maybe_intercept(self, cpu, bus) -> bool:
        """Called by Machine.step() before cpu.step(). Returns True if it
        handled a trapped LOAD/SAVE itself (the caller should not also
        call cpu.step() this cycle)."""
        if cpu.pc == LOAD_VECTOR:
            return self._handle_load(cpu, bus)
        if cpu.pc == SAVE_VECTOR:
            return self._handle_save(cpu, bus)
        return False

    def _device_and_name(self, cpu, bus) -> tuple[int, str] | None:
        device = bus.read8(DEVICE_ZP)
        if device < FIRST_VALID_DEVICE or device not in self.images:
            return None
        length = bus.read8(FILENAME_LEN_ZP)
        ptr = bus.read8(FILENAME_PTR_LO_ZP) | (bus.read8(FILENAME_PTR_HI_ZP) << 8)
        raw = bytes(bus.read8((ptr + i) & 0xFFFF) for i in range(length))
        name = raw.decode("ascii", errors="replace").upper()
        return device, name

    def _return_from_trap(self, cpu) -> None:
        """Simulate the real routine's own RTS back to the caller (which
        did JSR $FFD5/$FFD8), without ever executing the real ROM code
        at that address."""
        cpu.pc = (cpu.pull16() + 1) & 0xFFFF

    def _fail(self, cpu, error_code: int) -> bool:
        cpu.flags.c = True
        cpu.a = error_code
        self._return_from_trap(cpu)
        return True

    def _handle_load(self, cpu, bus) -> bool:
        result = self._device_and_name(cpu, bus)
        if result is None:
            return False  # not a device we're trapping -- let the real KERNAL handle it
        device, name = result
        image = self.images[device]

        if name in ("$", "$0", "$:*"):
            data = self._build_directory_listing(image)
        else:
            try:
                data = image.read_file(name)
            except FileNotFoundOnDisk:
                return self._fail(cpu, ERR_FILE_NOT_FOUND)

        # A PRG file's own first two bytes are always its own claimed load
        # address, and are always discarded from the actual loaded data
        # by real LOAD -- verified before writing this, not assumed:
        # secondary address only decides *which* address is used as the
        # destination (the file's own header value, or the caller's X/Y),
        # never whether the header bytes themselves become part of the
        # loaded content.
        if len(data) < 2:
            return self._fail(cpu, ERR_FILE_NOT_FOUND)
        secondary_address = bus.read8(SECONDARY_ADDR_ZP)
        if secondary_address == 0:
            load_address = cpu.x | (cpu.y << 8)
        else:
            load_address = data[0] | (data[1] << 8)
        payload = data[2:]

        for offset, byte in enumerate(payload):
            bus.write8((load_address + offset) & 0xFFFF, byte)

        end_address = (load_address + len(payload)) & 0xFFFF
        cpu.x, cpu.y = end_address & 0xFF, (end_address >> 8) & 0xFF
        cpu.flags.c = False
        self._return_from_trap(cpu)
        return True

    def _handle_save(self, cpu, bus) -> bool:
        result = self._device_and_name(cpu, bus)
        if result is None:
            return False
        device, name = result
        image = self.images[device]

        replace = name.startswith("@")
        if replace:
            name = name[1:]

        start_ptr_zp = cpu.a
        start_address = bus.read8(start_ptr_zp) | (bus.read8((start_ptr_zp + 1) & 0xFF) << 8)
        end_address = cpu.x | (cpu.y << 8)
        length = (end_address - start_address) & 0xFFFF
        data = bytes(bus.read8((start_address + i) & 0xFFFF) for i in range(length))

        # BASIC's SAVE doesn't hand the KERNAL the file's load address --
        # it must be written into the file itself so a later plain LOAD
        # (without ",1") can still relocate it correctly, matching the
        # real on-disk format every real PRG file uses.
        payload = bytes([start_address & 0xFF, (start_address >> 8) & 0xFF]) + data

        try:
            image.write_file(name, payload, overwrite=replace)
        except (FileExistsOnDisk, DiskFullError):
            # Verified against the real KERNAL error table before writing
            # this (an earlier version of this trap fabricated Carry-set
            # error codes for both cases that turned out not to exist --
            # the real KERNAL status table only has codes 1-9, none of
            # them "file exists" or "disk full"). Both are genuinely only
            # disk-error-channel conditions on real hardware (e.g. "63,
            # FILE EXISTS,00,00" or "72, DISK FULL,00,00", visible only
            # via OPEN 15,8,15 + INPUT#15, not modeled here) -- so the
            # KERNAL-level call itself just looks like it succeeded, and
            # the write silently doesn't happen. A real, sometimes-
            # confusing quirk of actual hardware, not a bug introduced by
            # this trap: a plain `SAVE"NAME",8` to an existing filename
            # gives no visible BASIC error unless the caller specifically
            # checks the error channel.
            cpu.flags.c = False
            self._return_from_trap(cpu)
            return True

        cpu.flags.c = False
        self._return_from_trap(cpu)
        return True

    def _build_directory_listing(self, image: D64Image) -> bytes:
        """A fake BASIC "program" representing the directory, in the same
        raw (unrechained) form a real drive sends -- see this module's
        docstring and DIRECTORY_LINK_PLACEHOLDER above."""
        lines = []

        header_text = b'"' + _petscii_display(image.disk_name, 16) + b'" ' + image.disk_id.encode("ascii").ljust(2) + b" 2A"
        lines.append((0, header_text))

        for entry in image.directory():
            type_name = {0: "DEL", 1: "SEQ", 2: "PRG", 3: "USR", 4: "REL"}.get(entry["file_type"], "???")
            name_field = b'"' + _petscii_display(entry["name"], 16) + b'"'
            blocks = entry["size_sectors"]
            # The block count is the BASIC *line number* itself (LIST
            # shows it automatically) -- it must not also appear as
            # literal text here, or it prints twice (caught by actually
            # running LOAD"$",8 + LIST and seeing "1 1  <name>", not
            # assumed correct from the byte layout alone).
            text = b"   " + name_field + b" " + type_name.encode("ascii")
            lines.append((blocks, text))

        lines.append((image.blocks_free(), b"BLOCKS FREE."))

        body = bytearray()
        for line_number, text in lines:
            body += bytes([DIRECTORY_LINK_PLACEHOLDER & 0xFF, (DIRECTORY_LINK_PLACEHOLDER >> 8) & 0xFF])
            body += bytes([line_number & 0xFF, (line_number >> 8) & 0xFF])
            body += text
            body += b"\x00"
        body += b"\x00\x00"  # end of program

        return bytes([DIRECTORY_LOAD_ADDRESS & 0xFF, (DIRECTORY_LOAD_ADDRESS >> 8) & 0xFF]) + bytes(body)


def _petscii_display(name: str, width: int) -> bytes:
    return name.encode("ascii", errors="replace")[:width].ljust(width, b" ")
