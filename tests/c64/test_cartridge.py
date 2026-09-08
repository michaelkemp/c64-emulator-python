import struct

import pytest

from c64.cartridge import Cartridge, UnsupportedCartridge

CRT_MAGIC = b"C64 CARTRIDGE   "
HEADER_LEN = 0x40


def _header(*, hardware_type: int = 0, exrom: int, game: int, name: bytes = b"") -> bytes:
    header = bytearray(HEADER_LEN)
    header[0x00:0x10] = CRT_MAGIC
    header[0x10:0x14] = struct.pack(">I", HEADER_LEN)
    header[0x14:0x16] = struct.pack(">H", 0x0100)
    header[0x16:0x18] = struct.pack(">H", hardware_type)
    header[0x18] = exrom
    header[0x19] = game
    header[0x20 : 0x20 + len(name)] = name
    return bytes(header)


def _chip(*, load_addr: int, data: bytes, chip_type: int = 0, bank: int = 0) -> bytes:
    packet = bytearray(16 + len(data))
    packet[0:4] = b"CHIP"
    packet[4:8] = struct.pack(">I", len(packet))
    packet[8:10] = struct.pack(">H", chip_type)
    packet[10:12] = struct.pack(">H", bank)
    packet[12:14] = struct.pack(">H", load_addr)
    packet[14:16] = struct.pack(">H", len(data))
    packet[16:] = data
    return bytes(packet)


def test_8k_cartridge_parses_roml_only(tmp_path):
    # Real 8K mode: GAME=1 (inactive line, byte value 1), EXROM=0 (active).
    path = tmp_path / "test.crt"
    path.write_bytes(_header(exrom=0, game=1) + _chip(load_addr=0x8000, data=bytes(range(256)) * 32))

    cart = Cartridge.from_file(path)

    assert cart.exrom == 0
    assert cart.game == 1
    assert cart.rom_lo == bytes(range(256)) * 32
    assert cart.rom_hi is None


def test_16k_cartridge_single_chip_splits_into_lo_and_hi(tmp_path):
    # Matches a real, working 16K cartridge (verified against an actual
    # Galaxian .crt image by hand before writing this): one 16KB CHIP
    # packet at $8000 covers both ROML and ROMH.
    path = tmp_path / "test.crt"
    lo = bytes([0xAA]) * 0x2000
    hi = bytes([0xBB]) * 0x2000
    path.write_bytes(_header(exrom=0, game=0) + _chip(load_addr=0x8000, data=lo + hi))

    cart = Cartridge.from_file(path)

    assert cart.rom_lo == lo
    assert cart.rom_hi == hi


def test_16k_cartridge_two_separate_chips(tmp_path):
    path = tmp_path / "test.crt"
    lo = bytes([0x11]) * 0x2000
    hi = bytes([0x22]) * 0x2000
    path.write_bytes(
        _header(exrom=0, game=0) + _chip(load_addr=0x8000, data=lo) + _chip(load_addr=0xA000, data=hi)
    )

    cart = Cartridge.from_file(path)

    assert cart.rom_lo == lo
    assert cart.rom_hi == hi


def test_name_is_read_and_null_stripped(tmp_path):
    path = tmp_path / "test.crt"
    path.write_bytes(_header(exrom=0, game=1, name=b"MY GAME") + _chip(load_addr=0x8000, data=bytes(0x2000)))

    cart = Cartridge.from_file(path)

    assert cart.name == "MY GAME"


def test_missing_signature_is_rejected(tmp_path):
    path = tmp_path / "test.crt"
    path.write_bytes(b"NOT A CARTRIDGE " + bytes(0x30))

    with pytest.raises(UnsupportedCartridge, match="not a .crt file"):
        Cartridge.from_file(path)


def test_non_generic_hardware_type_is_rejected(tmp_path):
    path = tmp_path / "test.crt"
    path.write_bytes(_header(hardware_type=5, exrom=0, game=1) + _chip(load_addr=0x8000, data=bytes(0x2000)))

    with pytest.raises(UnsupportedCartridge, match="hardware type 5"):
        Cartridge.from_file(path)


def test_ultimax_mode_is_rejected(tmp_path):
    path = tmp_path / "test.crt"
    path.write_bytes(_header(exrom=1, game=0) + _chip(load_addr=0x8000, data=bytes(0x2000)))

    with pytest.raises(UnsupportedCartridge, match="Ultimax"):
        Cartridge.from_file(path)


def test_no_cartridge_lines_are_rejected(tmp_path):
    path = tmp_path / "test.crt"
    path.write_bytes(_header(exrom=1, game=1) + _chip(load_addr=0x8000, data=bytes(0x2000)))

    with pytest.raises(UnsupportedCartridge, match="no cartridge"):
        Cartridge.from_file(path)


def test_bank_switched_chip_is_rejected(tmp_path):
    path = tmp_path / "test.crt"
    path.write_bytes(_header(exrom=0, game=1) + _chip(load_addr=0x8000, data=bytes(0x2000), bank=1))

    with pytest.raises(UnsupportedCartridge, match="bank"):
        Cartridge.from_file(path)


def test_non_rom_chip_type_is_rejected(tmp_path):
    path = tmp_path / "test.crt"
    path.write_bytes(_header(exrom=0, game=1) + _chip(load_addr=0x8000, data=bytes(0x2000), chip_type=1))

    with pytest.raises(UnsupportedCartridge, match="chip_type=1"):
        Cartridge.from_file(path)


def test_unexpected_load_address_is_rejected(tmp_path):
    path = tmp_path / "test.crt"
    path.write_bytes(_header(exrom=0, game=1) + _chip(load_addr=0x9000, data=bytes(0x2000)))

    with pytest.raises(UnsupportedCartridge, match="load address"):
        Cartridge.from_file(path)
