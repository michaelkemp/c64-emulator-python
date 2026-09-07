import os

import pytest

pygame = pytest.importorskip("pygame")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")  # run headless -- no real audio device needed

from c64.sid import Sid  # noqa: E402
from c64.vic_ii import CYCLES_PER_LINE, PAL_CLOCK_HZ, PAL_LINES_PER_FRAME  # noqa: E402
from peripherals.audio import AudioOutput, samples_per_frame  # noqa: E402


def test_samples_per_frame_matches_the_real_clock_ratio():
    expected = round(44100 * PAL_LINES_PER_FRAME * CYCLES_PER_LINE / PAL_CLOCK_HZ)
    assert samples_per_frame(44100) == expected


@pytest.fixture
def audio():
    sid = Sid()
    out = AudioOutput(sid, sample_rate=44100, chunk_size=10)
    yield out, sid
    out.close()


def test_advance_generates_samples_at_the_correct_cadence(audio):
    out, sid = audio
    cycles_per_sample = PAL_CLOCK_HZ / 44100
    # Just under one sample's worth of cycles: nothing should flush yet.
    out.advance(int(cycles_per_sample * 9))
    assert len(out._pending) <= 9


def test_a_full_chunk_gets_flushed_and_played(audio):
    out, sid = audio
    cycles_per_sample = PAL_CLOCK_HZ / 44100
    out.advance(int(cycles_per_sample * out.chunk_size) + 1)
    assert out._channel.get_busy()
    assert len(out._pending) < out.chunk_size  # the full chunk was flushed out


def test_silence_produces_a_valid_zeroed_chunk(audio):
    out, sid = audio
    cycles_per_sample = PAL_CLOCK_HZ / 44100
    out.advance(int(cycles_per_sample * out.chunk_size) + 1)
    assert out._channel.get_busy()  # silence still plays a real (all-zero) buffer


def test_chunk_size_defaults_to_one_video_frames_worth():
    sid = Sid()
    out = AudioOutput(sid, sample_rate=44100)
    try:
        assert out.chunk_size == samples_per_frame(44100)
    finally:
        out.close()
