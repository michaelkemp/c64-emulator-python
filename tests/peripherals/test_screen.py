import os

import pytest

pygame = pytest.importorskip("pygame")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # run headless -- no real display needed

from c64.vic_ii import CYCLES_PER_LINE, FRAME_HEIGHT, FRAME_WIDTH, PALETTE, PAL_LINES_PER_FRAME  # noqa: E402
from peripherals.screen import CYCLES_PER_FRAME, Screen, frame_to_rgb_bytes  # noqa: E402


def test_frame_to_rgb_bytes_maps_indices_through_the_palette():
    frame = [[0, 1], [2, 3]]
    result = frame_to_rgb_bytes(frame)
    expected = bytes(PALETTE[0]) + bytes(PALETTE[1]) + bytes(PALETTE[2]) + bytes(PALETTE[3])
    assert result == expected


def test_frame_to_rgb_bytes_produces_exactly_3_bytes_per_pixel():
    frame = [[0] * FRAME_WIDTH for _ in range(FRAME_HEIGHT)]
    result = frame_to_rgb_bytes(frame)
    assert len(result) == FRAME_WIDTH * FRAME_HEIGHT * 3


def test_cycles_per_frame_matches_pal_geometry():
    assert CYCLES_PER_FRAME == PAL_LINES_PER_FRAME * CYCLES_PER_LINE


@pytest.fixture
def screen():
    s = Screen(scale=1, target_fps=1000)
    yield s
    s.close()


def test_screen_opens_a_window_of_the_expected_scaled_size(screen):
    assert screen.window.get_size() == (FRAME_WIDTH, FRAME_HEIGHT)


def test_screen_draw_does_not_raise_and_updates_the_window(screen):
    frame = [[i % 16 for i in range(FRAME_WIDTH)] for _ in range(FRAME_HEIGHT)]
    screen.draw(frame)
    color = tuple(screen.window.get_at((0, 0)))[:3]
    assert color == PALETTE[0]


def test_poll_events_returns_true_with_no_pending_quit_event(screen):
    assert screen.poll_events() is True
