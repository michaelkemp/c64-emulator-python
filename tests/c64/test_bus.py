import pytest

from c64.bus import Bus
from c64.cartridge import Cartridge


class FakeChip:
    """Minimal RegisterChip: records every access, backed by a byte array."""

    def __init__(self, size):
        self.registers = bytearray(size)
        self.reads = []
        self.writes = []

    def read_register(self, offset):
        self.reads.append(offset)
        return self.registers[offset]

    def write_register(self, offset, value):
        self.writes.append((offset, value))
        self.registers[offset] = value


def make_rom(size, fill):
    return bytes([fill]) * size


@pytest.fixture
def bus():
    return Bus(
        basic_rom=make_rom(0x2000, 0xB0),
        kernal_rom=make_rom(0x2000, 0xE0),
        char_rom=make_rom(0x1000, 0xC0),
    )


def test_zero_page_ports_are_not_backed_by_ram(bus):
    bus.write8(0x0000, 0xFF)  # all bits as output, so the data byte reads back exactly
    bus.write8(0x0001, 0x35)
    assert bus.read8(0x0000) == 0xFF
    assert bus.read8(0x0001) == 0x35


def test_default_reset_state_shows_basic_io_and_kernal(bus):
    assert bus.read8(0xA000) == 0xB0  # BASIC ROM
    assert bus.read8(0xE000) == 0xE0  # KERNAL ROM
    # $D000 defaults to I/O (CHAREN=1): VIC-II register window, no chip
    # attached yet -> open bus.
    assert bus.read8(0xD000) == 0xFF


def test_plain_ram_regions_are_unaffected_by_banking(bus):
    bus.write8(0x0400, 0x93)
    bus.write8(0xC000, 0x42)
    assert bus.read8(0x0400) == 0x93
    assert bus.read8(0xC000) == 0x42


def test_basic_rom_hidden_when_loram_clear_but_ram_underneath_still_writable(bus):
    bus.write8(0x0000, 0xFF)
    bus.write8(0x0001, 0b1111_1110)  # LORAM=0, HIRAM=1, CHAREN=1
    assert bus.read8(0xA000) == 0x00  # RAM under the ROM, untouched so far

    bus.write8(0xA000, 0x77)
    assert bus.read8(0xA000) == 0x77  # RAM banked in, sees the write

    bus.write8(0x0001, 0b1111_1111)  # LORAM=1, HIRAM=1: BASIC ROM visible again
    assert bus.read8(0xA000) == 0xB0  # ROM overlay, RAM write now hidden


def test_kernal_rom_needs_only_hiram():
    bus = Bus(kernal_rom=make_rom(0x2000, 0xE0))
    bus.write8(0x0000, 0xFF)
    bus.write8(0x0001, 0b1111_1110)  # LORAM=0, HIRAM=1, CHAREN=1
    assert bus.read8(0xE000) == 0xE0


def test_hiram_clear_hides_kernal_rom_regardless_of_loram(bus):
    bus.write8(0x0000, 0xFF)
    bus.write8(0x0001, 0b1111_1101)  # LORAM=1, HIRAM=0, CHAREN=1
    assert bus.read8(0xE000) != 0xE0


def test_missing_rom_falls_back_to_ram():
    bus = Bus()  # no ROMs supplied at all
    bus.write8(0xA000, 0x11)
    bus.write8(0xE000, 0x22)
    assert bus.read8(0xA000) == 0x11
    assert bus.read8(0xE000) == 0x22


def test_charen_clear_shows_character_rom_and_hides_io(bus):
    bus.write8(0x0000, 0xFF)
    bus.write8(0x0001, 0b1111_1011)  # CHAREN=0
    assert bus.read8(0xD000) == 0xC0  # char ROM
    assert bus.read8(0xD800) == 0xC0  # still char ROM, not color RAM


def test_writes_under_character_rom_land_in_hidden_ram_not_visible_until_charen_set():
    bus = Bus(char_rom=make_rom(0x1000, 0xC0))
    bus.write8(0x0000, 0xFF)
    bus.write8(0x0001, 0b1111_1011)  # CHAREN=0: char ROM visible
    bus.write8(0xD020, 0x55)  # write lands in hidden RAM, not visible yet
    assert bus.read8(0xD020) == 0xC0

    bus.write8(0x0001, 0b1111_1111)  # CHAREN=1: I/O now selected, not RAM
    assert bus.read8(0xD020) == 0xFF  # VIC-II window, no chip attached -> open bus


def test_color_ram_only_stores_low_nibble(bus):
    bus.write8(0xD800, 0xFF)
    assert bus.read8(0xD800) == 0xFF  # low nibble 0xF, high nibble forced to 0xF

    bus.write8(0xD801, 0x10)  # low nibble 0x0
    assert bus.read8(0xD801) == 0xF0


def test_vic_sid_cia_windows_dispatch_to_the_attached_chip():
    vic, sid, cia1, cia2 = FakeChip(0x40), FakeChip(0x20), FakeChip(0x10), FakeChip(0x10)
    bus = Bus(vic=vic, sid=sid, cia1=cia1, cia2=cia2)

    bus.write8(0xD011, 0x1B)
    bus.write8(0xD418, 0x0F)
    bus.write8(0xDC0D, 0x81)
    bus.write8(0xDD00, 0x07)

    assert vic.registers[0x11] == 0x1B
    assert sid.registers[0x18] == 0x0F
    assert cia1.registers[0x0D] == 0x81
    assert cia2.registers[0x00] == 0x07

    assert bus.read8(0xD011) == 0x1B
    assert bus.read8(0xD418) == 0x0F
    assert bus.read8(0xDC0D) == 0x81
    assert bus.read8(0xDD00) == 0x07


def test_vic_register_window_mirrors_every_0x40_bytes():
    vic = FakeChip(0x40)
    bus = Bus(vic=vic)
    bus.write8(0xD011, 0x42)
    assert bus.read8(0xD051) == 0x42  # 0xD011 + 0x40, same underlying register


def test_cartridge_io_windows_are_open_bus(bus):
    assert bus.read8(0xDE00) == 0xFF
    assert bus.read8(0xDF00) == 0xFF
    bus.write8(0xDE00, 0x99)  # silently ignored, doesn't raise
    assert bus.read8(0xDE00) == 0xFF


def test_rom_size_is_validated():
    with pytest.raises(ValueError):
        Bus(basic_rom=b"\x00" * 100)


def test_vic_bank_defaults_to_bank_0_without_a_cia2(bus):
    assert bus.vic_bank_base() == 0x0000


def test_vic_bank_follows_cia2_port_a_bits_inverted():
    cia2 = FakeChip(0x10)
    bus = Bus(cia2=cia2)
    cia2.registers[0] = 0b11  # bank 0
    assert bus.vic_bank_base() == 0x0000
    cia2.registers[0] = 0b10  # bank 1
    assert bus.vic_bank_base() == 0x4000
    cia2.registers[0] = 0b01  # bank 2
    assert bus.vic_bank_base() == 0x8000
    cia2.registers[0] = 0b00  # bank 3
    assert bus.vic_bank_base() == 0xC000


def test_read_vic_sees_ram_independent_of_cpu_bank_switching():
    # CPU sees BASIC ROM at $A000 by default. Point the VIC-II at bank 2
    # ($8000-$BFFF, via CIA2) so its offset $2000 aliases the very same
    # physical address -- it should see the RAM underneath the ROM there,
    # a genuinely different view of the same address.
    cia2 = FakeChip(0x10)
    cia2.registers[0] = 0b01  # bank 2
    bus = Bus(basic_rom=make_rom(0x2000, 0xB0), cia2=cia2)

    bus.write8(0xA000, 0x42)  # lands in RAM regardless of what's banked in
    assert bus.read8(0xA000) == 0xB0  # CPU: ROM
    assert bus.read_vic(0x2000) == 0x42  # VIC-II (bank 2, offset $2000 = $A000): RAM


def test_read_vic_substitutes_char_rom_only_at_1000_in_banks_0_and_2():
    char_rom = make_rom(0x1000, 0xC0)
    cia2 = FakeChip(0x10)
    bus = Bus(char_rom=char_rom, cia2=cia2)

    cia2.registers[0] = 0b11  # bank 0 ($0000): char ROM visible at $1000-$1FFF
    assert bus.read_vic(0x1000) == 0xC0
    bus.write8(0x1000, 0x99)  # underlying RAM write, hidden behind the ROM view
    assert bus.read_vic(0x1000) == 0xC0

    cia2.registers[0] = 0b10  # bank 1 ($4000): no char ROM substitution at all
    assert bus.read_vic(0x1000) != 0xC0


def test_read_color_nibble_reads_the_low_nibble_directly():
    bus = Bus()
    bus.write8(0xD800, 0xAB)
    assert bus.read_color_nibble(0) == 0x0B


def make_cartridge(*, exrom, game, rom_lo=None, rom_hi=None):
    return Cartridge(name="TEST", exrom=exrom, game=game, rom_lo=rom_lo, rom_hi=rom_hi)


def test_no_cartridge_behaves_exactly_as_before(bus):
    # Bus() with no `cartridge` argument at all defaults to the real
    # "nothing plugged in" line state (EXROM=1, GAME=1) -- $8000-$9FFF
    # stays plain RAM, matching every pre-cartridge test above.
    assert bus.cart_exrom == 1 and bus.cart_game == 1
    bus.write8(0x8000, 0x42)
    assert bus.read8(0x8000) == 0x42


def test_8k_cartridge_roml_needs_loram_and_hiram():
    # Verified directly against VICE's own c64meminit_roml_config source
    # array, not assumed: ROML needs LORAM *and* HIRAM, not just EXROM.
    cart = make_cartridge(exrom=0, game=1, rom_lo=make_rom(0x2000, 0x99))
    bus = Bus(basic_rom=make_rom(0x2000, 0xB0), cartridge=cart)

    assert bus.read8(0x8000) == 0x99  # default reset state: LORAM=1, HIRAM=1
    assert bus.read8(0xA000) == 0xB0  # 8K mode: BASIC ROM still visible at $A000

    bus.write8(0x0000, 0xFF)
    bus.write8(0x0001, 0b1111_1110)  # LORAM=0, HIRAM=1
    assert bus.read8(0x8000) != 0x99  # ROML hidden -- RAM underneath instead


def test_8k_cartridge_writes_fall_through_to_ram_underneath():
    cart = make_cartridge(exrom=0, game=1, rom_lo=make_rom(0x2000, 0x99))
    bus = Bus(cartridge=cart)
    bus.write8(0x8000, 0x42)
    assert bus.read8(0x8000) == 0x99  # write hidden behind the ROM overlay

    bus.write8(0x0000, 0xFF)
    bus.write8(0x0001, 0b1111_1110)  # LORAM=0: ROML hidden, RAM write now visible
    assert bus.read8(0x8000) == 0x42


def test_16k_cartridge_romh_needs_only_hiram_not_loram():
    # The one genuinely surprising, verified-not-assumed asymmetry:
    # ROMH (16K mode) needs HIRAM but *not* LORAM, unlike ROML.
    cart = make_cartridge(exrom=0, game=0, rom_lo=make_rom(0x2000, 0x11), rom_hi=make_rom(0x2000, 0x22))
    bus = Bus(basic_rom=make_rom(0x2000, 0xB0), cartridge=cart)

    bus.write8(0x0000, 0xFF)
    bus.write8(0x0001, 0b1111_1110)  # LORAM=0, HIRAM=1
    assert bus.read8(0x8000) != 0x11  # ROML hidden (needs LORAM too)
    assert bus.read8(0xA000) == 0x22  # ROMH still visible (HIRAM alone is enough)


def test_16k_cartridge_romh_replaces_basic_rom():
    cart = make_cartridge(exrom=0, game=0, rom_lo=make_rom(0x2000, 0x11), rom_hi=make_rom(0x2000, 0x22))
    bus = Bus(basic_rom=make_rom(0x2000, 0xB0), cartridge=cart)
    assert bus.read8(0xA000) == 0x22  # cartridge ROMH, not BASIC ROM


def test_cartridge_romh_hidden_when_hiram_clear():
    cart = make_cartridge(exrom=0, game=0, rom_lo=make_rom(0x2000, 0x11), rom_hi=make_rom(0x2000, 0x22))
    bus = Bus(cartridge=cart)
    bus.write8(0x0000, 0xFF)
    bus.write8(0x0001, 0b1111_1101)  # HIRAM=0
    assert bus.read8(0xA000) != 0x22


def test_read16_write16_and_load_match_flat_memory_semantics(bus):
    bus.write16(0x0400, 0xBEEF)
    assert bus.read16(0x0400) == 0xBEEF
    assert bus.read8(0x0400) == 0xEF
    assert bus.read8(0x0401) == 0xBE

    bus.load(0x0800, bytes([1, 2, 3]))
    assert [bus.read8(0x0800 + i) for i in range(3)] == [1, 2, 3]


# --- Ultimax mode (EXROM=1, GAME=0) -- see Bus._read_ultimax/_write_ultimax ---
# for the real memory map, verified directly against VICE's c64meminit.c /
# c64cartmem.c source rather than assumed by symmetry with the non-Ultimax
# case.

def make_ultimax_cartridge(*, rom_lo=None, rom_hi=None):
    return make_cartridge(exrom=1, game=0, rom_lo=rom_lo, rom_hi=rom_hi)


def test_ultimax_flag_set_from_exrom_and_game():
    assert Bus(cartridge=make_ultimax_cartridge()).cart_ultimax is True
    assert Bus(cartridge=make_cartridge(exrom=0, game=1)).cart_ultimax is False
    assert Bus().cart_ultimax is False  # no cartridge -- EXROM=1/GAME=1, not Ultimax


def test_ultimax_zero_page_through_0fff_is_ordinary_ram():
    bus = Bus(cartridge=make_ultimax_cartridge())
    bus.write8(0x0002, 0x42)  # zero page (not the $00/$01 CPU port itself)
    bus.write8(0x0FFF, 0x99)
    assert bus.read8(0x0002) == 0x42
    assert bus.read8(0x0FFF) == 0x99


def test_ultimax_1000_7fff_and_a000_cfff_are_open_bus():
    bus = Bus(cartridge=make_ultimax_cartridge())
    for addr in (0x1000, 0x4000, 0x7FFF, 0xA000, 0xC000, 0xCFFF):
        assert bus.read8(addr) == 0xFF, hex(addr)


def test_ultimax_writes_to_1000_7fff_and_a000_cfff_have_no_effect():
    """Real hardware has no RAM write-select in this range in Ultimax
    mode -- writes are true no-ops, not lost-but-later-visible."""
    bus = Bus(cartridge=make_ultimax_cartridge())
    for addr in (0x1000, 0x4000, 0x7FFF, 0xA000, 0xC000, 0xCFFF):
        bus.write8(addr, 0x77)
        assert bus.read8(addr) == 0xFF, hex(addr)


def test_ultimax_roml_at_8000_reads_from_cartridge():
    cart = make_ultimax_cartridge(rom_lo=make_rom(0x2000, 0x11))
    bus = Bus(cartridge=cart)
    assert bus.read8(0x8000) == 0x11
    assert bus.read8(0x9FFF) == 0x11


def test_ultimax_8000_9fff_open_bus_without_a_roml_chip():
    bus = Bus(cartridge=make_ultimax_cartridge())  # no rom_lo at all
    assert bus.read8(0x8000) == 0xFF


def test_ultimax_write_to_8000_9fff_never_reaches_ram_even_with_roml_present():
    """The real surprise: verified against VICE's own roml_store -- for a
    generic cartridge in Ultimax mode, $8000-$9FFF writes are a genuine
    no-op, unlike the non-Ultimax case where ROM-overlaid writes land in
    the RAM underneath."""
    cart = make_ultimax_cartridge(rom_lo=make_rom(0x2000, 0x11))
    bus = Bus(cartridge=cart)
    bus.write8(0x8000, 0x77)
    assert bus.read8(0x8000) == 0x11  # unchanged -- still the cartridge ROM


def test_ultimax_romh_at_e000_replaces_kernal():
    cart = make_ultimax_cartridge(rom_hi=make_rom(0x2000, 0x22))
    bus = Bus(kernal_rom=make_rom(0x2000, 0xB0), cartridge=cart)
    assert bus.read8(0xE000) == 0x22
    assert bus.read8(0xFFFF) == 0x22  # including the reset/IRQ/NMI vector bytes


def test_ultimax_e000_ffff_open_bus_without_a_romh_chip():
    bus = Bus(kernal_rom=make_rom(0x2000, 0xB0), cartridge=make_ultimax_cartridge())
    assert bus.read8(0xE000) == 0xFF  # not the KERNAL -- Ultimax mode hides it entirely


def test_ultimax_write_to_e000_ffff_never_reaches_ram():
    cart = make_ultimax_cartridge(rom_hi=make_rom(0x2000, 0x22))
    bus = Bus(cartridge=cart)
    bus.write8(0xE000, 0x77)
    assert bus.read8(0xE000) == 0x22  # unchanged


def test_ultimax_d000_dfff_is_always_io_regardless_of_charen():
    """Unlike the non-Ultimax case, CHAREN has no effect at all on
    $D000-$DFFF once Ultimax mode is active -- verified against VICE's
    own memory-config table (all Ultimax rows show "io" unconditionally)."""
    bus = Bus(char_rom=make_rom(0x1000, 0xAA), cartridge=make_ultimax_cartridge())
    bus.write8(0x0000, 0xFF)
    bus.write8(0x0001, 0b1111_1011)  # CHAREN=0 -- would normally show char ROM
    bus.write8(0xD800, 0x03)  # color RAM
    assert bus.read8(0xD800) & 0x0F == 0x03  # I/O (color RAM), not char ROM's 0xAA

