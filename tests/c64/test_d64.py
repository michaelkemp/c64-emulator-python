import pytest

from c64.d64 import (
    DATA_BYTES_PER_SECTOR,
    FILE_TYPE_PRG,
    IMAGE_SIZE,
    D64Image,
    DiskFullError,
    FileExistsOnDisk,
    FileNotFoundOnDisk,
)


def test_blank_image_is_the_real_174848_byte_size():
    image = D64Image.create_blank("MY DISK")
    assert len(image.to_bytes()) == IMAGE_SIZE == 174848


def test_blank_image_reports_the_real_664_blocks_free():
    """A famous, well-known real-hardware fact: a freshly-formatted 1541
    disk reports exactly "664 BLOCKS FREE." -- a strong, independently
    verifiable sanity check on the BAM math (683 total sectors minus
    track 18's own 19, which the real convention excludes entirely from
    the free-blocks count)."""
    image = D64Image.create_blank("MY DISK")
    assert image.blocks_free() == 664


def test_blank_image_has_no_directory_entries():
    image = D64Image.create_blank("MY DISK")
    assert image.directory() == []


def test_disk_name_and_id_round_trip():
    image = D64Image.create_blank("TEST DISK", disk_id="8A")
    assert image.disk_name == "TEST DISK"
    assert image.disk_id == "8A"


def test_write_then_read_small_file_round_trips_exactly():
    image = D64Image.create_blank("MY DISK")
    data = b"\x01\x08\x0b\x08\x0a\x00\x99\x22HELLO\x22\x00\x00\x00"
    image.write_file("HELLO", data)
    assert image.read_file("HELLO") == data


def test_write_then_read_exactly_one_sector_of_data():
    image = D64Image.create_blank("MY DISK")
    data = bytes(range(DATA_BYTES_PER_SECTOR))  # exactly 254 bytes -- one full sector
    image.write_file("EXACT", data)
    assert image.read_file("EXACT") == data


def test_write_then_read_multi_sector_file_round_trips_exactly():
    image = D64Image.create_blank("MY DISK")
    data = bytes((i * 7) % 256 for i in range(2000))  # spans multiple sectors
    image.write_file("BIGFILE", data)
    assert image.read_file("BIGFILE") == data


def test_write_file_appears_in_directory_with_correct_metadata():
    image = D64Image.create_blank("MY DISK")
    image.write_file("PROGRAM", b"x" * 500, file_type=FILE_TYPE_PRG)

    entries = image.directory()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["name"] == "PROGRAM"
    assert entry["file_type"] == FILE_TYPE_PRG
    assert entry["closed"] is True
    assert entry["size_sectors"] == 2  # ceil(500 / 254)


def test_write_file_consumes_free_blocks():
    image = D64Image.create_blank("MY DISK")
    before = image.blocks_free()
    image.write_file("PROGRAM", b"x" * 500)
    after = image.blocks_free()
    assert before - after == 2  # ceil(500 / 254) sectors


def test_write_existing_name_without_overwrite_raises():
    image = D64Image.create_blank("MY DISK")
    image.write_file("PROGRAM", b"hello")
    with pytest.raises(FileExistsOnDisk):
        image.write_file("PROGRAM", b"world")


def test_write_existing_name_with_overwrite_replaces_content():
    image = D64Image.create_blank("MY DISK")
    image.write_file("PROGRAM", b"hello")
    image.write_file("PROGRAM", b"a longer replacement", overwrite=True)
    assert image.read_file("PROGRAM") == b"a longer replacement"
    assert len(image.directory()) == 1  # not duplicated


def test_read_nonexistent_file_raises():
    image = D64Image.create_blank("MY DISK")
    with pytest.raises(FileNotFoundOnDisk):
        image.read_file("NOPE")


def test_delete_file_frees_its_sectors_and_removes_directory_entry():
    image = D64Image.create_blank("MY DISK")
    before = image.blocks_free()
    image.write_file("PROGRAM", b"x" * 500)
    image.delete_file("PROGRAM")
    assert image.blocks_free() == before
    assert image.directory() == []
    with pytest.raises(FileNotFoundOnDisk):
        image.read_file("PROGRAM")


def test_directory_grows_past_one_sector_of_entries():
    """8 entries fit in the first directory sector; the 9th must extend
    the chain onto a second directory-track sector -- exercise that path
    for real, not just the common case."""
    image = D64Image.create_blank("MY DISK")
    for i in range(9):
        image.write_file(f"FILE{i}", bytes([i]) * 10)

    entries = image.directory()
    assert len(entries) == 9
    assert {e["name"] for e in entries} == {f"FILE{i}" for i in range(9)}
    for i in range(9):
        assert image.read_file(f"FILE{i}") == bytes([i]) * 10


def test_disk_full_raises_a_specific_error():
    image = D64Image.create_blank("MY DISK")
    huge = b"x" * (image.blocks_free() * DATA_BYTES_PER_SECTOR + 1000)
    with pytest.raises(DiskFullError):
        image.write_file("TOOBIG", huge)


def test_save_and_load_round_trip_through_a_real_file(tmp_path):
    image = D64Image.create_blank("MY DISK")
    image.write_file("PROGRAM", b"some real program bytes")
    path = tmp_path / "test.d64"
    image.save(path)

    reloaded = D64Image.load(path)
    assert reloaded.read_file("PROGRAM") == b"some real program bytes"
    assert reloaded.disk_name == "MY DISK"
