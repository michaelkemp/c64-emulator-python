"""Real audio output for `Sid.output_sample()` (pygame.mixer).

Requires this project's `peripherals` extra (`pip install -e
".[peripherals]"`).

`AudioOutput.advance(cycles)` -- called with the same cycle count
`Machine.step()` returns, exactly like `CIA6526.tick`/`VicII.tick` --
accumulates PHI2 cycles and calls `Sid.output_sample()` once every
`cycles_per_sample` (the real PAL clock divided by the output sample
rate), so generated audio has the **correct pitch**: sample generation
is tied to real emulated cycles, not wall-clock time, regardless of how
fast or slow this process actually runs them.

**Honest performance caveat, not a bug in this module**: `docs/
machine.md`'s own profiling shows this project's unoptimized pure-Python
core runs slower than real time once SID ticking is enabled
(`Machine(enable_audio=True)` -- by far the most expensive of the four
chips ticked every cycle). Since audio generation can't outrun real-time
consumption on hardware where the whole simulation itself runs slower
than real-time, sustained playback may have audible gaps under load --
an expected consequence of the documented performance profile, not
something this module tries to paper over. No wall-clock pacing was
added to `Machine` for this (a dedicated speed effort was explicitly
deferred, not part of this phase) -- samples still play in whatever
chunks the simulation manages to produce them.
"""

from __future__ import annotations

import array

import pygame

from c64.sid import Sid
from c64.vic_ii import CYCLES_PER_LINE, PAL_CLOCK_HZ, PAL_LINES_PER_FRAME

CYCLES_PER_FRAME = PAL_LINES_PER_FRAME * CYCLES_PER_LINE


def samples_per_frame(sample_rate: int) -> int:
    """How many audio samples one real PAL video frame's worth of PHI2
    cycles corresponds to -- the natural chunk size to pace playback
    against the existing per-frame main loop."""
    return round(sample_rate * CYCLES_PER_FRAME / PAL_CLOCK_HZ)


def _to_int16(sample: float) -> int:
    return max(-32768, min(32767, round(sample * 32767)))


class AudioOutput:
    def __init__(self, sid: Sid, sample_rate: int = 44100, chunk_size: int | None = None) -> None:
        pygame.mixer.init(frequency=sample_rate, size=-16, channels=1)
        self.sid = sid
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size if chunk_size is not None else samples_per_frame(sample_rate)
        self._cycles_per_sample = PAL_CLOCK_HZ / sample_rate
        self._cycle_accumulator = 0.0
        self._pending: list[int] = []
        self._channel = pygame.mixer.Channel(0)

    def advance(self, cycles: int) -> None:
        """Feed in the cycle count from a `Machine.step()` call. Reads
        `Sid.output_sample()` (never ticks it -- that's `Machine`'s job)
        once per accumulated sample period, queuing/playing chunks of
        `chunk_size` samples as they fill up."""
        self._cycle_accumulator += cycles
        while self._cycle_accumulator >= self._cycles_per_sample:
            self._cycle_accumulator -= self._cycles_per_sample
            self._pending.append(_to_int16(self.sid.output_sample()))
            if len(self._pending) >= self.chunk_size:
                self._flush_chunk()

    def _flush_chunk(self) -> None:
        buf = array.array("h", self._pending[: self.chunk_size])
        del self._pending[: self.chunk_size]
        sound = pygame.mixer.Sound(buffer=buf.tobytes())
        if self._channel.get_busy():
            self._channel.queue(sound)
        else:
            self._channel.play(sound)

    def close(self) -> None:
        pygame.mixer.quit()
