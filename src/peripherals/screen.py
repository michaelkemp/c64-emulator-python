"""A real window showing what the VIC-II produces (pygame).

Requires this project's `peripherals` extra (`pip install -e
".[peripherals]"`) -- the emulation core itself has no dependency on
this or on pygame.

Real-time pacing, almost for free: `CYCLES_PER_FRAME` is exactly one PAL
frame's worth of PHI2 cycles (`PAL_LINES_PER_FRAME * CYCLES_PER_LINE`).
Running the machine for exactly that many cycles between each display
update, and capping the display to the real PAL rate (`target_fps`),
happens to keep the *simulated* machine running at approximately real
C64 speed too -- without this being the dedicated wall-clock pacing
`docs/machine.md` still flags as missing (that's Phase 10, once real
audio needs genuinely precise timing). It's a side effect good enough
for watching the screen update at a sane pace.

**`target_fps` must be the *exact* rate these constants imply, not a
rounded "50"**: `PAL_CLOCK_HZ / CYCLES_PER_FRAME` is ~50.1245Hz, not
50.0 -- real PAL C64s really do run slightly above 50Hz (a well-known,
correctly-cited fact, not this project's own rounding). A hardcoded
`target_fps=50` found this way: it paces the loop to a real 20.000ms/
iteration, but one iteration's worth of *audio* content is only
CYCLES_PER_FRAME/PAL_CLOCK_HZ = ~19.951ms -- a persistent ~0.25%
shortfall, not just random scheduling jitter, that slowly starves
`AudioOutput`'s buffered chunks over a sustained note. Caught while
diagnosing real playback that came out choppy even after `AudioOutput`
itself stopped dropping chunks (see its own module docstring) -- this
was the other half of the real cause.
"""

from __future__ import annotations

import pygame

from c64.vic_ii import CYCLES_PER_LINE, FRAME_HEIGHT, FRAME_WIDTH, PALETTE, PAL_CLOCK_HZ, PAL_LINES_PER_FRAME

CYCLES_PER_FRAME = PAL_LINES_PER_FRAME * CYCLES_PER_LINE
REAL_PAL_FPS = PAL_CLOCK_HZ / CYCLES_PER_FRAME  # ~50.1245Hz, not 50.0 -- see module docstring

_PALETTE_BYTES = [bytes(rgb) for rgb in PALETTE]


def frame_to_rgb_bytes(frame: list[list[int]]) -> bytes:
    """Convert a `VicII.render_frame()` indexed-color grid to flat RGB
    bytes, row-major -- the only part of this module that doesn't touch
    pygame, so it's testable without a display."""
    return b"".join(_PALETTE_BYTES[index] for row in frame for index in row)


class Screen:
    def __init__(self, scale: int = 2, target_fps: float = REAL_PAL_FPS) -> None:
        pygame.init()
        pygame.display.set_caption("c64-emulator-python")
        self.scale = scale
        self.target_fps = target_fps
        self.window = pygame.display.set_mode((FRAME_WIDTH * scale, FRAME_HEIGHT * scale))
        self.clock = pygame.time.Clock()

    def draw(self, frame: list[list[int]]) -> None:
        surface = pygame.image.frombuffer(frame_to_rgb_bytes(frame), (FRAME_WIDTH, FRAME_HEIGHT), "RGB")
        # Scale-to-a-new-surface then blit, not transform.scale(..., dest)
        # -- the in-place destination form requires the source and
        # destination to already share a pixel format, which isn't
        # guaranteed (caught by tests/peripherals/test_screen.py).
        scaled = pygame.transform.scale(surface, self.window.get_size())
        self.window.blit(scaled, (0, 0))
        pygame.display.flip()

    def tick(self) -> None:
        self.clock.tick(self.target_fps)

    def poll_events(self) -> bool:
        """Process pending window events. Returns False if the window
        was closed (the caller should stop running)."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
        return True

    def close(self) -> None:
        pygame.quit()
