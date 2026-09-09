""".d64 disk image format: parsing, directory listing, file read/write,
and blank-image creation.

See docs/disk.md for the verified format reference (BAM layout,
directory entry layout, file-data sector chain) this is built against,
and the KERNAL-trap protocol (`src/c64/disk_drive.py`) this exists to
support.

Deliberate simplifications, disclosed rather than silently assumed:
filenames are handled as plain uppercase ASCII, not full PETSCII
(lowercase/graphics character mapping isn't needed until real software
requires it); sector allocation is simple ascending track/sector order,
not real DOS's interleave-of-10 scheme (interleave only matters for
physical disk rotation/seek timing, not correctness, here).
"""

from __future__ import annotations

from pathlib import Path

SECTORS_PER_TRACK: list[int] = [21] * 17 + [19] * 7 + [18] * 6 + [17] * 5
TRACK_COUNT = len(SECTORS_PER_TRACK)
assert TRACK_COUNT == 35

SECTOR_SIZE = 256
TOTAL_SECTORS = sum(SECTORS_PER_TRACK)
IMAGE_SIZE = TOTAL_SECTORS * SECTOR_SIZE  # 174,848 bytes

DIRECTORY_TRACK = 18
BAM_SECTOR = 0
FIRST_DIRECTORY_SECTOR = 1
DIRECTORY_ENTRY_SIZE = 32
DIRECTORY_ENTRIES_PER_SECTOR = SECTOR_SIZE // DIRECTORY_ENTRY_SIZE  # 8

FILE_TYPE_DEL = 0
FILE_TYPE_SEQ = 1
FILE_TYPE_PRG = 2
FILE_TYPE_USR = 3
FILE_TYPE_REL = 4
FILE_CLOSED_BIT = 0x80
FILE_LOCKED_BIT = 0x40

PETSCII_PAD = 0xA0
DATA_BYTES_PER_SECTOR = SECTOR_SIZE - 2  # first 2 bytes are the chain link


class DiskFullError(Exception):
    """No free sector (or no free directory slot/sector) available."""


class FileNotFoundOnDisk(Exception):
    """No directory entry matches the requested name."""


class FileExistsOnDisk(Exception):
    """A directory entry with this name already exists (SAVE without replace)."""


def sectors_in_track(track: int) -> int:
    return SECTORS_PER_TRACK[track - 1]


def _track_start_sector_index(track: int) -> int:
    return sum(SECTORS_PER_TRACK[: track - 1])


def _sector_offset(track: int, sector: int) -> int:
    return (_track_start_sector_index(track) + sector) * SECTOR_SIZE


def _petscii_name(name: str) -> bytes:
    raw = name.encode("ascii", errors="replace").upper()[:16]
    return raw.ljust(16, bytes([PETSCII_PAD]))


def _from_petscii_name(raw: bytes) -> str:
    return raw.rstrip(bytes([PETSCII_PAD])).decode("ascii", errors="replace")


class D64Image:
    def __init__(self, data: bytearray) -> None:
        if len(data) != IMAGE_SIZE:
            raise ValueError(f"D64 image must be exactly {IMAGE_SIZE} bytes, got {len(data)}")
        self.data = data

    # -- construction / (de)serialization --------------------------------

    @classmethod
    def create_blank(cls, disk_name: str, disk_id: str = "2A") -> "D64Image":
        image = cls(bytearray(IMAGE_SIZE))
        bam = image._sector_view(DIRECTORY_TRACK, BAM_SECTOR)
        bam[0], bam[1] = DIRECTORY_TRACK, FIRST_DIRECTORY_SECTOR
        bam[2] = 0x41  # DOS version

        for track in range(1, TRACK_COUNT + 1):
            total = sectors_in_track(track)
            if track == DIRECTORY_TRACK:
                # Sectors 0 (BAM) and 1 (first directory sector) start
                # reserved; everything else on this track is free for
                # more directory sectors if the directory grows.
                bitmap = ((1 << total) - 1) & ~0b11
                free_count = total - 2
            else:
                bitmap = (1 << total) - 1
                free_count = total
            image._write_bam_entry(track, free_count, bitmap)

        bam[0x90:0xA0] = _petscii_name(disk_name)
        bam[0xA0], bam[0xA1] = PETSCII_PAD, PETSCII_PAD
        bam[0xA2:0xA4] = disk_id.encode("ascii", errors="replace")[:2].ljust(2, b" ")
        bam[0xA4] = PETSCII_PAD
        bam[0xA5:0xA7] = b"2A"
        bam[0xA7:0xAB] = bytes([PETSCII_PAD] * 4)
        return image

    @classmethod
    def from_bytes(cls, data: bytes) -> "D64Image":
        return cls(bytearray(data))

    @classmethod
    def load(cls, path: Path | str) -> "D64Image":
        return cls.from_bytes(Path(path).read_bytes())

    def to_bytes(self) -> bytes:
        return bytes(self.data)

    def save(self, path: Path | str) -> None:
        Path(path).write_bytes(self.to_bytes())

    # -- BAM (Block Availability Map) ------------------------------------

    def _bam_entry_offset(self, track: int) -> int:
        return 0x04 + (track - 1) * 4

    def _read_bam_entry(self, track: int) -> tuple[int, int]:
        bam = self._sector_view(DIRECTORY_TRACK, BAM_SECTOR)
        offset = self._bam_entry_offset(track)
        bitmap = bam[offset + 1] | (bam[offset + 2] << 8) | (bam[offset + 3] << 16)
        return bam[offset], bitmap

    def _write_bam_entry(self, track: int, free_count: int, bitmap: int) -> None:
        bam = self._sector_view(DIRECTORY_TRACK, BAM_SECTOR)
        offset = self._bam_entry_offset(track)
        bam[offset] = free_count
        bam[offset + 1] = bitmap & 0xFF
        bam[offset + 2] = (bitmap >> 8) & 0xFF
        bam[offset + 3] = (bitmap >> 16) & 0xFF

    def _is_sector_free(self, track: int, sector: int) -> bool:
        _, bitmap = self._read_bam_entry(track)
        return bool(bitmap & (1 << sector))

    def _set_sector_free(self, track: int, sector: int, free: bool) -> None:
        _, bitmap = self._read_bam_entry(track)
        if free:
            bitmap |= 1 << sector
        else:
            bitmap &= ~(1 << sector)
        self._write_bam_entry(track, bin(bitmap).count("1"), bitmap)

    def blocks_free(self) -> int:
        return sum(self._read_bam_entry(t)[0] for t in range(1, TRACK_COUNT + 1) if t != DIRECTORY_TRACK)

    @property
    def disk_name(self) -> str:
        bam = self._sector_view(DIRECTORY_TRACK, BAM_SECTOR)
        return _from_petscii_name(bytes(bam[0x90:0xA0]))

    @property
    def disk_id(self) -> str:
        bam = self._sector_view(DIRECTORY_TRACK, BAM_SECTOR)
        return bytes(bam[0xA2:0xA4]).decode("ascii", errors="replace")

    # -- sector access ----------------------------------------------------

    def _sector_view(self, track: int, sector: int) -> memoryview:
        offset = _sector_offset(track, sector)
        return memoryview(self.data)[offset : offset + SECTOR_SIZE]

    def _allocate_data_sectors(self, count: int) -> list[tuple[int, int]]:
        allocated: list[tuple[int, int]] = []
        for track in range(1, TRACK_COUNT + 1):
            if track == DIRECTORY_TRACK:
                continue
            for sector in range(sectors_in_track(track)):
                if len(allocated) >= count:
                    break
                if self._is_sector_free(track, sector):
                    allocated.append((track, sector))
            if len(allocated) >= count:
                break
        if len(allocated) < count:
            raise DiskFullError(f"need {count} free sectors, only {len(allocated)} available")
        for track, sector in allocated:
            self._set_sector_free(track, sector, False)
        return allocated

    def _allocate_directory_sector(self) -> tuple[int, int]:
        for sector in range(sectors_in_track(DIRECTORY_TRACK)):
            if self._is_sector_free(DIRECTORY_TRACK, sector):
                self._set_sector_free(DIRECTORY_TRACK, sector, False)
                return DIRECTORY_TRACK, sector
        raise DiskFullError("directory track is full")

    def _free_chain(self, track: int, sector: int) -> None:
        seen: set[tuple[int, int]] = set()
        while track != 0 and (track, sector) not in seen:
            seen.add((track, sector))
            view = self._sector_view(track, sector)
            next_track, next_sector = view[0], view[1]
            self._set_sector_free(track, sector, True)
            track, sector = next_track, next_sector

    # -- directory ----------------------------------------------------------

    def directory(self) -> list[dict]:
        entries = []
        track, sector = DIRECTORY_TRACK, FIRST_DIRECTORY_SECTOR
        seen: set[tuple[int, int]] = set()
        while track != 0 and (track, sector) not in seen:
            seen.add((track, sector))
            view = self._sector_view(track, sector)
            next_track, next_sector = view[0], view[1]
            for i in range(DIRECTORY_ENTRIES_PER_SECTOR):
                base = i * DIRECTORY_ENTRY_SIZE
                file_type_byte = view[base + 2]
                if file_type_byte == 0:
                    continue  # empty slot
                entries.append(
                    {
                        "name": _from_petscii_name(bytes(view[base + 5 : base + 21])),
                        "file_type": file_type_byte & 0x0F,
                        "closed": bool(file_type_byte & FILE_CLOSED_BIT),
                        "locked": bool(file_type_byte & FILE_LOCKED_BIT),
                        "first_track": view[base + 3],
                        "first_sector": view[base + 4],
                        "size_sectors": view[base + 30] | (view[base + 31] << 8),
                    }
                )
            track, sector = next_track, next_sector
        return entries

    def _find_entry(self, name: str) -> dict | None:
        for entry in self.directory():
            if entry["name"] == name:
                return entry
        return None

    def _add_directory_entry(
        self, name: str, file_type: int, first_track: int, first_sector: int, size_sectors: int
    ) -> None:
        track, sector = DIRECTORY_TRACK, FIRST_DIRECTORY_SECTOR
        while True:
            view = self._sector_view(track, sector)
            for i in range(DIRECTORY_ENTRIES_PER_SECTOR):
                base = i * DIRECTORY_ENTRY_SIZE
                if view[base + 2] == 0:
                    view[base + 2] = file_type | FILE_CLOSED_BIT
                    view[base + 3] = first_track
                    view[base + 4] = first_sector
                    view[base + 5 : base + 21] = _petscii_name(name)
                    view[base + 30] = size_sectors & 0xFF
                    view[base + 31] = (size_sectors >> 8) & 0xFF
                    return
            next_track, next_sector = view[0], view[1]
            if next_track == 0:
                next_track, next_sector = self._allocate_directory_sector()
                view[0], view[1] = next_track, next_sector
            track, sector = next_track, next_sector

    # -- file read/write --------------------------------------------------

    def read_file(self, name: str) -> bytes:
        entry = self._find_entry(name)
        if entry is None:
            raise FileNotFoundOnDisk(name)
        track, sector = entry["first_track"], entry["first_sector"]
        chunks = []
        seen: set[tuple[int, int]] = set()
        while track != 0 and (track, sector) not in seen:
            seen.add((track, sector))
            view = self._sector_view(track, sector)
            next_track, next_sector = view[0], view[1]
            if next_track == 0:
                chunks.append(bytes(view[2 : next_sector + 1]))
            else:
                chunks.append(bytes(view[2:SECTOR_SIZE]))
            track, sector = next_track, next_sector
        return b"".join(chunks)

    def delete_file(self, name: str) -> None:
        track, sector = DIRECTORY_TRACK, FIRST_DIRECTORY_SECTOR
        seen: set[tuple[int, int]] = set()
        while track != 0 and (track, sector) not in seen:
            seen.add((track, sector))
            view = self._sector_view(track, sector)
            next_track, next_sector = view[0], view[1]
            for i in range(DIRECTORY_ENTRIES_PER_SECTOR):
                base = i * DIRECTORY_ENTRY_SIZE
                if view[base + 2] == 0:
                    continue
                if _from_petscii_name(bytes(view[base + 5 : base + 21])) == name:
                    self._free_chain(view[base + 3], view[base + 4])
                    view[base + 2] = 0
                    return
            track, sector = next_track, next_sector
        raise FileNotFoundOnDisk(name)

    def write_file(self, name: str, data: bytes, file_type: int = FILE_TYPE_PRG, *, overwrite: bool = False) -> None:
        if self._find_entry(name) is not None:
            if not overwrite:
                raise FileExistsOnDisk(name)
            self.delete_file(name)

        sectors_needed = max(1, -(-len(data) // DATA_BYTES_PER_SECTOR))  # ceil division
        allocated = self._allocate_data_sectors(sectors_needed)

        for i, (track, sector) in enumerate(allocated):
            view = self._sector_view(track, sector)
            chunk = data[i * DATA_BYTES_PER_SECTOR : (i + 1) * DATA_BYTES_PER_SECTOR]
            if i + 1 < len(allocated):
                view[0], view[1] = allocated[i + 1]
            else:
                view[0] = 0
                view[1] = len(chunk) + 1  # offset of the last valid data byte
            view[2 : 2 + len(chunk)] = chunk

        first_track, first_sector = allocated[0]
        self._add_directory_entry(name, file_type, first_track, first_sector, sectors_needed)
