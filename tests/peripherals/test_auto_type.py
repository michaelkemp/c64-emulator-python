from c64.keyboard_matrix import KEY_POSITIONS, KeyboardMatrix
from peripherals.auto_type import GAP_FRAMES, HOLD_FRAMES, AutoTyper


def test_busy_reflects_queued_and_in_progress_state():
    typer = AutoTyper(KeyboardMatrix())
    assert typer.busy is False
    typer.type_text("A")
    assert typer.busy is True
    for _ in range(HOLD_FRAMES + GAP_FRAMES + 1):  # +1: the initial idle->holding pump itself
        typer.pump()
    assert typer.busy is False


def test_a_plain_letter_is_pressed_then_released():
    matrix = KeyboardMatrix()
    typer = AutoTyper(matrix)
    typer.type_text("A")

    typer.pump()  # first pump starts the press
    assert matrix.is_pressed(*KEY_POSITIONS["A"])

    for _ in range(HOLD_FRAMES - 1):
        typer.pump()
    assert matrix.is_pressed(*KEY_POSITIONS["A"])  # still held through the hold window

    typer.pump()  # crosses into the gap phase -- released now
    assert not matrix.is_pressed(*KEY_POSITIONS["A"])


def test_return_maps_to_the_return_key():
    matrix = KeyboardMatrix()
    typer = AutoTyper(matrix)
    typer.type_text("\n")
    typer.pump()
    assert matrix.is_pressed(*KEY_POSITIONS["RETURN"])


def test_shifted_punctuation_presses_both_keys_together():
    matrix = KeyboardMatrix()
    typer = AutoTyper(matrix)
    typer.type_text('"')
    typer.pump()
    assert matrix.is_pressed(*KEY_POSITIONS["LSHIFT"])
    assert matrix.is_pressed(*KEY_POSITIONS["2"])
    for _ in range(HOLD_FRAMES):
        typer.pump()
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
        typer.pump()
        assert matrix.is_pressed(*KEY_POSITIONS["LSHIFT"]), ch
        assert matrix.is_pressed(*KEY_POSITIONS[base_key]), ch


def test_unmappable_character_is_skipped_without_getting_stuck():
    matrix = KeyboardMatrix()
    typer = AutoTyper(matrix)
    typer.type_text("☃A")  # unicode snowman, then a real letter
    typer.pump()  # the snowman is skipped immediately
    typer.pump()  # now 'A' should start
    assert matrix.is_pressed(*KEY_POSITIONS["A"])


def test_multiple_characters_do_not_overlap():
    matrix = KeyboardMatrix()
    typer = AutoTyper(matrix)
    typer.type_text("AB")

    typer.pump()
    assert matrix.is_pressed(*KEY_POSITIONS["A"])
    assert not matrix.is_pressed(*KEY_POSITIONS["B"])

    for _ in range(HOLD_FRAMES + GAP_FRAMES):
        typer.pump()
    assert not matrix.is_pressed(*KEY_POSITIONS["A"])

    typer.pump()
    assert matrix.is_pressed(*KEY_POSITIONS["B"])


def test_full_program_line_drains_the_queue_eventually():
    matrix = KeyboardMatrix()
    typer = AutoTyper(matrix)
    typer.type_text('10 PRINT "HI"\n')
    for _ in range(1000):
        if not typer.busy:
            break
        typer.pump()
    assert not typer.busy
