import array

import pytest

sd = pytest.importorskip("sounddevice")

from c64.sid import Sid  # noqa: E402
from c64.vic_ii import PAL_CLOCK_HZ  # noqa: E402
from peripherals.audio import AudioOutput  # noqa: E402


@pytest.fixture
def audio():
    """A real `AudioOutput`, with its background playback stream
    stopped immediately -- these tests check buffer/generation logic
    deterministically, without a real, concurrently-running callback
    thread racing to consume samples out from under the assertions.
    Skips (rather than failing) if this environment has no real audio
    device at all."""
    sid = Sid()
    try:
        out = AudioOutput(sid, sample_rate=44100)
    except sd.PortAudioError:
        pytest.skip("no real audio device available in this environment")
    out._stream.stop()
    yield out, sid
    out.close()


def test_advance_generates_samples_at_the_correct_cadence(audio):
    out, sid = audio
    cycles_per_sample = PAL_CLOCK_HZ / 44100
    out.advance(int(cycles_per_sample * 9) + 1)
    assert len(out._buffer) == 9


def test_buffered_seconds_reflects_whats_waiting(audio):
    out, sid = audio
    cycles_per_sample = PAL_CLOCK_HZ / 44100
    out.advance(int(cycles_per_sample * 4410))  # 100ms worth
    assert out.buffered_seconds() == pytest.approx(0.1, rel=0.05)


def test_silence_still_produces_real_samples(audio):
    # Silence (SID never ticked/gated) is a valid, real all-zero signal --
    # it should still be appended to the buffer, not skipped.
    out, sid = audio
    cycles_per_sample = PAL_CLOCK_HZ / 44100
    out.advance(int(cycles_per_sample * 100))
    assert out.buffered_seconds() > 0


def test_callback_pulls_available_samples_in_order(audio):
    # The callback is plain, device-independent logic, callable directly.
    out, sid = audio
    with out._lock:
        out._buffer.extend([100, 200, 300])
    buf = bytearray(5 * 2)  # 5 frames, 16-bit mono
    out._callback(buf, 5, None, None)
    values = array.array("h", bytes(buf))
    assert list(values) == [100, 200, 300, 0, 0]  # real samples first, then silence
    assert out.buffered_seconds() == 0  # fully drained, not left behind


def test_callback_pads_with_silence_on_underrun_not_an_exception(audio):
    # An empty buffer (generation hasn't kept up) must produce silence,
    # not raise -- a graceful underrun, unlike the old chunk-queueing
    # design's silent chunk drops.
    out, sid = audio
    buf = bytearray(10 * 2)
    out._callback(buf, 10, None, None)
    assert list(array.array("h", bytes(buf))) == [0] * 10


def test_close_stops_and_closes_the_stream_cleanly():
    sid = Sid()
    try:
        out = AudioOutput(sid, sample_rate=44100)
    except sd.PortAudioError:
        pytest.skip("no real audio device available in this environment")
    out.close()
    assert out._stream.closed
