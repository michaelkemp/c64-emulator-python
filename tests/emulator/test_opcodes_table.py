from c6502.emulator.opcodes import OPCODES


def test_no_duplicate_or_out_of_range_opcodes():
    assert len(OPCODES) == len(set(OPCODES))
    assert all(0 <= opcode <= 0xFF for opcode in OPCODES)


def test_every_entry_has_callable_functions_and_a_mnemonic():
    for opcode, spec in OPCODES.items():
        assert spec.mnemonic
        assert spec.mode
        assert callable(spec.addressing_fn)
        assert callable(spec.instruction_fn)
        assert spec.base_cycles > 0
