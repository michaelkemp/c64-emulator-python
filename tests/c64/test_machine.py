from c6502.asm import assemble

from c64.machine import Machine


def test_machine_constructs_and_resets_without_roms():
    m = Machine()
    assert m.cpu.pc == m.bus.read16(0xFFFC)


def test_step_returns_the_real_instruction_cycle_count():
    m = Machine()
    m.bus.write16(0xFFFC, 0x0810)
    m.bus.load(0x0810, bytes([0xEA]))  # NOP = 2 cycles
    m.cpu.reset()
    assert m.step() == 2


def test_step_advances_every_chip_by_the_same_cycles():
    m = Machine()
    m.bus.write16(0xFFFC, 0x0810)
    m.bus.load(0x0810, bytes([0xEA]))  # NOP
    m.cpu.reset()
    m.step()
    # NOP is 2 cycles -- nowhere near a full raster line (63), so the VIC-II
    # shouldn't have advanced a line, but its internal cycle accumulator
    # should reflect exactly 2 cycles having been fed to it.
    assert m.vic.current_raster == 0
    assert m.vic._cycles_into_line == 2


def test_run_executes_the_requested_number_of_steps_and_sums_cycles():
    m = Machine()
    m.bus.write16(0xFFFC, 0x0810)
    m.bus.load(0x0810, bytes([0xEA, 0xEA, 0xEA]))
    m.cpu.reset()
    total = m.run(3)
    assert total == 6
    assert m.cpu.pc == 0x0813


def test_irq_is_delivered_when_cia1_timer_fires():
    source = """
        .org $0810
    start:
        CLI
        LDA #$05
        STA $DC04       ; CIA1 timer A low
        LDA #$00
        STA $DC05       ; CIA1 timer A high (period=5)
        LDA #$81
        STA $DC0D       ; enable timer A interrupt
        LDA #$01
        STA $DC0E       ; start timer, continuous
    loop:
        INC $02
        JMP loop
    irq:
        INC $03
        RTI
        .org $FFFE
        .word irq
        .org $FFFC
        .word start
    """
    image = assemble(source)
    m = Machine()
    m.bus.load(image.origin, image.data)
    m.cpu.reset()

    m.run(200)

    assert m.bus.read8(0x03) > 0  # the IRQ handler actually ran


def test_nmi_is_delivered_once_per_edge_from_cia2():
    source = """
        .org $0810
    start:
        LDA #$05
        STA $DD04       ; CIA2 timer A low
        LDA #$00
        STA $DD05       ; CIA2 timer A high (period=5)
        LDA #$81
        STA $DD0D       ; enable timer A interrupt
        LDA #$01
        STA $DD0E       ; start timer, continuous
    loop:
        JMP loop
    nmi:
        INC $03
        RTI
        .org $FFFA
        .word nmi
        .org $FFFC
        .word start
    """
    image = assemble(source)
    m = Machine()
    m.bus.load(image.origin, image.data)
    m.cpu.reset()

    # The NMI handler never clears CIA2's ICR, so the line stays asserted
    # for the rest of the run -- edge-triggering means it should still
    # only have fired exactly once.
    m.run(500)

    assert m.bus.read8(0x03) == 1


def test_from_roms_loads_files_from_the_given_directory(tmp_path):
    (tmp_path / "kernal").write_bytes(bytes([0xE0]) * 0x2000)
    (tmp_path / "basic").write_bytes(bytes([0xB0]) * 0x2000)
    (tmp_path / "chargen").write_bytes(bytes([0xC0]) * 0x1000)

    m = Machine.from_roms(tmp_path)

    assert m.bus.kernal_rom[0] == 0xE0
    assert m.bus.basic_rom[0] == 0xB0
    assert m.bus.char_rom[0] == 0xC0


def test_from_roms_tolerates_a_missing_rom(tmp_path):
    (tmp_path / "kernal").write_bytes(bytes([0xE0]) * 0x2000)
    m = Machine.from_roms(tmp_path)
    assert m.bus.kernal_rom is not None
    assert m.bus.basic_rom is None
    assert m.bus.char_rom is None
