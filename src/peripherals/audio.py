"""Real audio output for `Sid.output_sample()`, via `sounddevice`'s
callback-driven PortAudio streaming.

Requires this project's `peripherals` extra (`pip install -e
".[peripherals]"`).

`AudioOutput.advance(cycles)` -- called with the same cycle count
`Machine.step()` returns, exactly like `CIA6526.tick`/`VicII.tick` --
accumulates PHI2 cycles and calls `Sid.output_sample()` once every
`cycles_per_sample` (the real PAL clock divided by the output sample
rate), appending each generated sample to a shared buffer. So generated
audio has the **correct pitch**: sample generation is tied to real
emulated cycles, not wall-clock time, regardless of how fast or slow
this process actually runs them.

**Why this isn't `pygame.mixer` (its previous implementation)**: real
playback through `pygame.mixer.Channel` -- queueing successive
`pygame.mixer.Sound` objects end-to-end -- produced audible artifacts at
every chunk boundary, confirmed to *not* be a data problem two
independent ways (a raw `Sid.output_sample()` capture bypassing pygame
entirely, and a capture of `AudioOutput`'s own produced chunk *content*
in creation order, both showed a perfectly continuous waveform with no
discontinuity at any chunk boundary), and not plain pygame.mixer misuse
either (`scripts/pygame_tone_test.py`, independently-generated
sine/triangle tones via a single `.play()` call, sounded clean). What
was left, pointing squarely at `pygame.mixer` itself: real playback came
out with artifacts specifically clustered at the quiet, rapidly-decaying
*end* of each note -- consistent with some per-`Sound`-object effect
(declick/resampling-filter reset or similar) that's masked by a loud
sustain and audible against a quiet release, independent of the actual
sample data (already proven continuous).

`sounddevice` (PortAudio) sidesteps the entire question: there are no
discrete chunk/`Sound` objects at all here. `advance()` just appends
samples to a plain `collections.deque`; a background thread PortAudio
manages calls `_callback` whenever the real hardware needs more data,
pulling directly from that deque (filling any shortfall with silence,
not by-hand chunk queueing). Continuous by construction, not by careful
timing.

**Switching to `sounddevice` uncovered a second, genuinely separate
problem, since fixed in `scripts/run_c64.py` (not here)**: a continuous
pull-based stream has no tolerance at all for `Machine`'s own per-frame
cost exceeding real-time, whereas `pygame.mixer`'s old "only play a
fully-completed chunk" design accidentally *couldn't* expose this (a
slow chunk just started late; it never played a *partial*, patchy one).
Directly measured: with real video rendering enabled every frame,
`machine.step()` (~12.3ms) + `render_frame()` (~3.7ms) +
`Screen.draw()` (~8.2ms) totals ~24.2ms against a 19.95ms real-time
budget -- a structural deficit *before any margin at all* -- confirmed
by watching `buffered_seconds()` stay pinned near zero for 8+ real
seconds with drawing enabled every frame, and genuinely climb once
`run_c64.py` throttles drawing to 1-in-5 frames while still stepping
CPU/audio every frame. See `scripts/run_c64.py`'s
`VIDEO_DRAW_EVERY_WITH_AUDIO` for the fix and the full numbers.
"""

from __future__ import annotations

import array
import threading
from collections import deque

import sounddevice as sd

from c64.sid import Sid
from c64.vic_ii import PAL_CLOCK_HZ


def _to_int16(sample: float) -> int:
    return max(-32768, min(32767, round(sample * 32767)))


class AudioOutput:
    def __init__(self, sid: Sid, sample_rate: int = 44100) -> None:
        self.sid = sid
        self.sample_rate = sample_rate
        self._cycles_per_sample = PAL_CLOCK_HZ / sample_rate
        self._cycle_accumulator = 0.0
        self._lock = threading.Lock()
        self._buffer: deque[int] = deque()
        self._stream = sd.RawOutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            callback=self._callback,
        )
        self._stream.start()

    def advance(self, cycles: int) -> None:
        """Feed in the cycle count from a `Machine.step()` call. Reads
        `Sid.output_sample()` (never ticks it -- that's `Machine`'s job)
        once per accumulated sample period, appending to the shared
        buffer the background audio thread pulls from."""
        self._cycle_accumulator += cycles
        new_samples = []
        while self._cycle_accumulator >= self._cycles_per_sample:
            self._cycle_accumulator -= self._cycles_per_sample
            new_samples.append(_to_int16(self.sid.output_sample()))
        if new_samples:
            with self._lock:
                self._buffer.extend(new_samples)

    def buffered_seconds(self) -> float:
        """How much generated audio is waiting, not yet pulled by the
        real-time playback thread -- purely informational (e.g. for
        logging/diagnostics); nothing needs to poll this to avoid
        dropping data the way the old chunk-queueing design did."""
        with self._lock:
            return len(self._buffer) / self.sample_rate

    def _callback(self, outdata, frames: int, _time_info, _status) -> None:
        """Runs on PortAudio's own real-time thread, not the main
        thread -- pulls up to `frames` samples out of the shared buffer,
        padding with silence if generation hasn't kept up (a graceful
        underrun: silence, not a click or a dropped/overwritten chunk)."""
        with self._lock:
            available = min(frames, len(self._buffer))
            samples = [self._buffer.popleft() for _ in range(available)]
        if available < frames:
            samples.extend([0] * (frames - available))
        outdata[:] = array.array("h", samples).tobytes()

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()
