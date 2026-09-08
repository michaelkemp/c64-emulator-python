from c64.keyboard_matrix import KEY_POSITIONS, KeyboardMatrix
from peripherals.auto_type import GAP_CYCLES, HOLD_CYCLES, AutoTyper

# Small per-call increments, mirroring how scripts/run_c64.py actually
# drives this (feeding in whatever cycle count Machine.step() returns per
# instruction -- typically a handful of cycles), not one huge call.
STEP = 100


def run_cycles(typer: AutoTyper, total: int) -> None:
    remaining = total
    while remaining > 0:
        chunk = min(STEP, remaining)
        typer.advance(chunk)
        remaining -= chunk


def test_busy_reflects_queued_and_in_progress_state():
    typer = AutoTyper(KeyboardMatrix())
    assert typer.busy is False
    typer.type_text("A")
    assert typer.busy is True
    run_cycles(typer, HOLD_CYCLES + GAP_CYCLES + STEP)
    assert typer.busy is False


def test_a_plain_letter_is_pressed_then_released():
    matrix = KeyboardMatrix()
    typer = AutoTyper(matrix)
    typer.type_text("A")

    typer.advance(1)  # first advance starts the press
    assert matrix.is_pressed(*KEY_POSITIONS["A"])

    run_cycles(typer, HOLD_CYCLES - STEP)
    assert matrix.is_pressed(*KEY_POSITIONS["A"])  # still held through the hold window

    run_cycles(typer, STEP * 2)  # crosses into the gap phase -- released now
    assert not matrix.is_pressed(*KEY_POSITIONS["A"])


def test_return_maps_to_the_return_key():
    matrix = KeyboardMatrix()
    typer = AutoTyper(matrix)
    typer.type_text("\n")
    typer.advance(1)
    assert matrix.is_pressed(*KEY_POSITIONS["RETURN"])


def test_shifted_punctuation_presses_both_keys_together():
    matrix = KeyboardMatrix()
    typer = AutoTyper(matrix)
    typer.type_text('"')
    typer.advance(1)
    assert matrix.is_pressed(*KEY_POSITIONS["LSHIFT"])
    assert matrix.is_pressed(*KEY_POSITIONS["2"])
    run_cycles(typer, HOLD_CYCLES)
    assert not matrix.is_pressed(*KEY_POSITIONS["LSHIFT"])
    assert not matrix.is_pressed(*KEY_POSITIONS["2"])


def test_comparison_and_question_mark_characters_are_mapped():
    # Regression test: an earlier version silently dropped <, >, and ?
    # entirely (they weren't in the character table at all), which
    # corrupted real BASIC ("IF X<24" typed as "IF X24") rather than
    # raising -- caught by actually running a typed program, not just
    # inspecting the mapping table. Verified empirically, same as
    # KeyboardMatrix.KEY_POSITIONS: SHIFT+COMMA='<', SHIFT+PERIOD='>',
    # SHIFT+SLASH='?'.
    for ch, base_key in (("<", "COMMA"), (">", "PERIOD"), ("?", "SLASH")):
        matrix = KeyboardMatrix()
        typer = AutoTyper(matrix)
        typer.type_text(ch)
        typer.advance(1)
        assert matrix.is_pressed(*KEY_POSITIONS["LSHIFT"]), ch
        assert matrix.is_pressed(*KEY_POSITIONS[base_key]), ch


def test_shifted_number_row_symbols_are_mapped():
    # Regression test: an earlier version silently dropped #, $, and %
    # entirely -- the last gap in the SHIFT+number-row pattern (1/2/6/7/8/9
    # were already covered, 3/4/5 never filled in). $ specifically
    # corrupted a real BASIC program using a string array (`DIM WN$(4)`
    # typed as `DIM WN(4)`, a numeric array), which then raised a real
    # ?TYPE MISMATCH ERROR the moment it tried to store a string into it
    # -- caught by actually running the program through the real KERNAL,
    # not by inspecting the mapping table. Verified empirically via GETIN,
    # same as KeyboardMatrix.KEY_POSITIONS: SHIFT+3='#', SHIFT+4='$',
    # SHIFT+5='%'.
    for ch, base_key in (("#", "3"), ("$", "4"), ("%", "5")):
        matrix = KeyboardMatrix()
        typer = AutoTyper(matrix)
        typer.type_text(ch)
        typer.advance(1)
        assert matrix.is_pressed(*KEY_POSITIONS["LSHIFT"]), ch
        assert matrix.is_pressed(*KEY_POSITIONS[base_key]), ch


def test_unmappable_character_is_skipped_without_getting_stuck():
    matrix = KeyboardMatrix()
    typer = AutoTyper(matrix)
    typer.type_text("☃A")  # unicode snowman, then a real letter
    typer.advance(1)  # the snowman is skipped immediately
    typer.advance(1)  # now 'A' should start
    assert matrix.is_pressed(*KEY_POSITIONS["A"])


def test_multiple_characters_do_not_overlap():
    matrix = KeyboardMatrix()
    typer = AutoTyper(matrix)
    typer.type_text("AB")

    typer.advance(1)
    assert matrix.is_pressed(*KEY_POSITIONS["A"])
    assert not matrix.is_pressed(*KEY_POSITIONS["B"])

    run_cycles(typer, HOLD_CYCLES + GAP_CYCLES)
    assert not matrix.is_pressed(*KEY_POSITIONS["A"])

    typer.advance(1)
    assert matrix.is_pressed(*KEY_POSITIONS["B"])


def test_full_program_line_drains_the_queue_eventually():
    matrix = KeyboardMatrix()
    typer = AutoTyper(matrix)
    typer.type_text('10 PRINT "HI"\n')
    total_budget = len('10 PRINT "HI"\n') * (HOLD_CYCLES + GAP_CYCLES) * 2  # generous
    run_cycles(typer, total_budget)
    assert not typer.busy


def test_hold_and_gap_cycle_counts_clear_one_full_jiffy_irq_period():
    # See module docstring: a held key must survive at least one full
    # ~16,421-cycle CIA1 Timer A jiffy IRQ period, or it can land entirely
    # between two of the KERNAL's keyboard scans and be dropped. An
    # earlier version of this guard only checked against a much smaller
    # (and wrong) empirically-"verified" minimum, measured by a harness
    # that didn't actually drive the real interrupt-driven scan -- see
    # test_auto_type_integration.py for the real, ROM-booted regression
    # test that caught this. This test just guards against someone
    # tightening the constants back down without re-running that.
    JIFFY_IRQ_PERIOD = 16_421
    assert HOLD_CYCLES > JIFFY_IRQ_PERIOD
    assert GAP_CYCLES > JIFFY_IRQ_PERIOD
