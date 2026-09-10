"""Real, end-to-end tests of the KERNAL-trap disk emulation (strategy 1
-- see docs/disk.md) -- boot the actual staged KERNAL+BASIC, type real
commands via AutoTyper, and check the real screen/disk-image results,
the same way this project verifies its other chips against genuine ROM
behavior rather than mocking it.

Gated behind the same ROM-staging requirement as the rest of the real-
KERNAL tests in this directory (skip cleanly if roms/c64/ isn't staged).
"""

from pathlib import Path

import pytest

from c64.d64 import D64Image
from c64.machine import Machine
from c64.vic_ii import CYCLES_PER_LINE, PAL_LINES_PER_FRAME
from peripherals.auto_type import AutoTyper

CYCLES_PER_FRAME = PAL_LINES_PER_FRAME * CYCLES_PER_LINE  # same computation peripherals/screen.py uses

ROMS_DIR = Path(__file__).resolve().parent.parent.parent / "roms" / "c64"
pytestmark = pytest.mark.skipif(not (ROMS_DIR / "kernal").exists(), reason="ROMs not staged (see scripts/stage_roms.sh)")

BOOT_SETTLE_FRAMES = 150


def _run_frames(machine: Machine, frames: int) -> None:
    for _ in range(frames):
        total = 0
        while total < CYCLES_PER_FRAME:
            total += machine.step()


def _boot_and_type(machine: Machine, text: str) -> AutoTyper:
    auto_typer = AutoTyper(machine.keyboard)
    _run_frames(machine, BOOT_SETTLE_FRAMES)
    auto_typer.type_text(text)
    while auto_typer.busy:
        auto_typer.advance(machine.step())
    _run_frames(machine, 30)
    return auto_typer


def _screen_text(machine: Machine) -> list[str]:
    def screen_code_to_char(c: int) -> str:
        if 1 <= c <= 26:
            return chr(c + 64)
        if 32 <= c <= 63:
            return chr(c)
        return " "

    screen = bytes(machine.bus.read8(0x0400 + i) for i in range(40 * 25))
    return ["".join(screen_code_to_char(b) for b in screen[r * 40 : (r + 1) * 40]) for r in range(25)]


@pytest.fixture
def machine():
    return Machine.from_roms(str(ROMS_DIR))


def test_save_produces_a_byte_perfect_real_prg_file(machine):
    """Verified independently by hand once already (see CLAUDE.md's
    changelog) -- locking in that exact byte-for-byte result: $0801 load
    address, real BASIC tokenization (PRINT=$99, END=$80), real line
    numbers, real end-of-program terminator."""
    disk = D64Image.create_blank("MY DISK")
    machine.disk_drives.mount(8, disk)

    _boot_and_type(machine, '10 PRINT "HELLO FROM DISK"\r20 END\rSAVE"HELLO",8\r')

    assert disk.directory()[0]["name"] == "HELLO"
    saved = disk.read_file("HELLO")
    assert saved == (
        b"\x01\x08"  # load address $0801
        b"\x19\x08\x0a\x00\x99 \x22HELLO FROM DISK\x22\x00"  # line 10
        b"\x1f\x08\x14\x00\x80\x00"  # line 20
        b"\x00\x00"  # end of program
    )


def test_load_and_run_a_previously_saved_program_end_to_end():
    """The real round trip: one machine SAVEs, a completely different,
    freshly-booted machine LOADs the same disk image and RUNs it --
    proving the saved file is independently correct, not just an
    artifact of one machine's own state."""
    disk = D64Image.create_blank("MY DISK")

    saver = Machine.from_roms(str(ROMS_DIR))
    saver.disk_drives.mount(8, disk)
    _boot_and_type(saver, '10 PRINT "HELLO FROM DISK"\r20 END\rSAVE"HELLO",8\r')

    loader = Machine.from_roms(str(ROMS_DIR))
    loader.disk_drives.mount(8, disk)
    _boot_and_type(loader, 'LOAD"HELLO",8\rRUN\r')

    assert "HELLO FROM DISK" in "".join(_screen_text(loader))


def test_directory_listing_matches_real_c64_format(machine):
    disk = D64Image.create_blank("MY DISK", disk_id="8A")
    disk.write_file("HELLO", b"\x01\x08" + b"x" * 20)
    disk.write_file("GOODBYE", b"\x01\x08" + b"x" * 20)
    machine.disk_drives.mount(8, disk)

    _boot_and_type(machine, 'LOAD"$",8\rLIST\r')

    lines = [line.rstrip() for line in _screen_text(machine) if line.strip()]
    assert '0 "MY DISK         " 8A 2A' in lines
    assert '1    "HELLO           " PRG' in lines
    assert '1    "GOODBYE         " PRG' in lines
    assert f"{disk.blocks_free()} BLOCKS FREE." in lines


def test_load_nonexistent_file_gives_the_real_basic_error(machine):
    disk = D64Image.create_blank("MY DISK")
    machine.disk_drives.mount(8, disk)

    _boot_and_type(machine, 'LOAD"NOPE",8\r')

    assert any("FILE NOT FOUND" in line for line in _screen_text(machine))


def test_wildcard_load_gets_the_first_program_on_the_disk():
    """Reproduces a real, reported session: LOAD"*",8,1 on a disk with a
    saved program used to give a real ?FILE NOT FOUND ERROR, because the
    drive was matching "*" as a literal filename instead of a wildcard."""
    disk = D64Image.create_blank("MY DISK")

    saver = Machine.from_roms(str(ROMS_DIR))
    saver.disk_drives.mount(8, disk)
    _boot_and_type(saver, '10 PRINT "HELLO FROM DISK"\r20 END\rSAVE"HELLO",8\r')

    loader = Machine.from_roms(str(ROMS_DIR))
    loader.disk_drives.mount(8, disk)
    _boot_and_type(loader, 'LOAD"*",8,1\rRUN\r')

    screen = "".join(_screen_text(loader))
    assert "FILE NOT FOUND" not in screen
    assert "HELLO FROM DISK" in screen


def test_wildcard_load_with_a_prefix_matches_by_name(machine):
    disk = D64Image.create_blank("MY DISK")
    disk.write_file("OTHER", b"\x01\x08" + b"x" * 20)
    disk.write_file("PACMAN", b"\x01\x08" + b"y" * 20)
    machine.disk_drives.mount(8, disk)

    _boot_and_type(machine, 'LOAD"PAC*",8\r')

    assert not any("FILE NOT FOUND" in line for line in _screen_text(machine))


def test_two_drives_stay_independent_by_device_number():
    disk8 = D64Image.create_blank("DRIVE EIGHT")
    disk9 = D64Image.create_blank("DRIVE NINE")
    machine = Machine.from_roms(str(ROMS_DIR))
    machine.disk_drives.mount(8, disk8)
    machine.disk_drives.mount(9, disk9)

    _boot_and_type(
        machine,
        '10 PRINT "FROM DRIVE 8"\rSAVE"PROG8",8\r'
        '10 PRINT "FROM DRIVE 9"\rSAVE"PROG9",9\r',
    )

    assert [e["name"] for e in disk8.directory()] == ["PROG8"]
    assert [e["name"] for e in disk9.directory()] == ["PROG9"]


def test_save_at_replaces_an_existing_file(machine):
    disk = D64Image.create_blank("MY DISK")
    machine.disk_drives.mount(8, disk)

    _boot_and_type(
        machine,
        '10 PRINT "FIRST"\rSAVE"PROG",8\r'
        '10 PRINT "SECOND"\rSAVE"@PROG",8\r',
    )

    assert len(disk.directory()) == 1
    assert b"SECOND" in disk.read_file("PROG")


def test_save_without_replace_to_an_existing_name_silently_does_not_overwrite(machine):
    """A real, verified-before-implementing quirk, not a bug: the real
    KERNAL error table (sta.c64.org/cbm64krnerr.html) only defines codes
    1-9 -- there's no KERNAL-level "FILE EXISTS" error at all. That's a
    disk-error-channel-only condition (visible via OPEN 15,8,15 +
    INPUT#15, not modeled here), so a plain `SAVE"NAME",8` to an existing
    name looks like it succeeded from BASIC's own perspective -- no
    visible error -- while genuinely, correctly, not overwriting the
    file. Confirmed by an earlier version of this trap fabricating a
    Carry-set error code that doesn't really exist, producing garbled
    on-screen text instead of a clean message when actually run."""
    disk = D64Image.create_blank("MY DISK")
    machine.disk_drives.mount(8, disk)

    _boot_and_type(machine, '10 PRINT "FIRST"\rSAVE"PROG",8\r10 PRINT "SECOND"\rSAVE"PROG",8\r')

    assert not any("?" in line and "ERROR" in line for line in _screen_text(machine))
    assert len(disk.directory()) == 1
    assert b"FIRST" in disk.read_file("PROG")  # unchanged, not overwritten


def test_unmounted_device_falls_through_to_the_real_kernal_error(machine):
    """No disk mounted at all for device 8 -- the trap must not fire, and
    the real, unmodified KERNAL's own error should show through."""
    _boot_and_type(machine, 'LOAD"ANYTHING",8\r')
    assert any("DEVICE NOT PRESENT" in line for line in _screen_text(machine))
