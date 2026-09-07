from c64.cpu_port import CpuPort


def test_reset_state_floats_all_bits_high():
    port = CpuPort()
    assert port.read_data() == 0xFF
    assert port.loram is True
    assert port.hiram is True
    assert port.charen is True


def test_ddr_output_bits_reflect_latch():
    port = CpuPort()
    port.write_ddr(0xFF)
    port.write_data(0x00)
    assert port.read_data() == 0x00
    assert port.loram is False
    assert port.hiram is False
    assert port.charen is False


def test_ddr_input_bits_still_float_high_regardless_of_latch():
    port = CpuPort()
    port.write_ddr(0x00)
    port.write_data(0x00)  # latch value is irrelevant for input bits
    assert port.read_data() == 0xFF


def test_mixed_ddr_combines_driven_and_floating_bits():
    port = CpuPort()
    port.write_ddr(0b0000_0111)  # only LORAM/HIRAM/CHAREN are outputs
    port.write_data(0b0000_0010)  # HIRAM set, LORAM and CHAREN clear
    assert port.loram is False
    assert port.hiram is True
    assert port.charen is False
    assert port.read_data() == 0b1111_1010


def test_ddr_register_is_independently_readable():
    port = CpuPort()
    port.write_ddr(0x2F)
    assert port.read_ddr() == 0x2F
