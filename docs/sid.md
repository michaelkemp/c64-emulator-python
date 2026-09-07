# MOS 6581/8580 SID

Three independent voices (waveform generator + ADSR envelope), a shared
analog-style filter, and a master volume stage. This is explicitly the
chip the roadmap calls "the most forgiving to get close enough early" --
unlike VIC-II timing, close approximations are genuinely fine here, and
this file says exactly where each approximation is.

Primary reference: the official MOS 6581 datasheet
([6502.org PDF](https://6502.org/documents/datasheets/mos/mos_6581_sid.pdf)).
[reSID](https://github.com/daglem/reSID) (GPL) is the standard reference
implementation for understanding the real analog filter's non-linear
behavior -- studied for concepts only, per `docs/testing-strategy.md`'s
license discipline; nothing here is copied from it. This implementation
is closer in spirit to the many textbook/community "good enough" SID
emulators than to reSID's meticulously reverse-engineered transistor-level
model.

## Register map (per voice, ×3: voice `n` at offset `n*7`)

| Offset (+7n) | Name | Purpose |
|---|---|---|
| `$00` | FREQLO | Frequency, low 8 bits |
| `$01` | FREQHI | Frequency, high 8 bits (16-bit total) |
| `$02` | PWLO | Pulse width, low 8 bits |
| `$03` | PWHI | Pulse width, high 4 bits (12-bit total) |
| `$04` | CR | Control: bit0=GATE, bit1=SYNC, bit2=RING MOD, bit3=TEST, bits4-7=waveform (triangle/sawtooth/pulse/noise) |
| `$05` | AD | bits4-7=Attack rate, bits0-3=Decay rate |
| `$06` | SR | bits4-7=Sustain level, bits0-3=Release rate |

Shared registers:

| Offset | Name | Purpose |
|---|---|---|
| `$15` | FCLO | Filter cutoff, low 3 bits |
| `$16` | FCHI | Filter cutoff, high 8 bits (11-bit total) |
| `$17` | RES/FILT | bits4-7=resonance, bits0-2=filter enable (voice 1/2/3), bit3=external input to filter (not modeled -- no external audio source exists) |
| `$18` | MODE/VOL | bits0-3=master volume, bit4=low-pass, bit5=band-pass, bit6=high-pass, bit7=voice 3 disconnect (mute voice 3 from the final mix without stopping it -- it can still be used purely as an `OSC3`/`ENV3` modulation source) |
| `$19` | POTX | Paddle X (not modeled -- no paddle input exists; reads `$FF`) |
| `$1A` | POTY | Paddle Y (not modeled; reads `$FF`) |
| `$1B` | OSC3 | Voice 3's current waveform output, top 8 bits -- read-only, lets software use voice 3 as a free-running pseudo-random/modulation source without hearing it |
| `$1C` | ENV3 | Voice 3's current envelope level -- read-only, same idea |
| `$1D`-`$1F` | -- | Unconnected; read `$FF`, writes ignored |

Every register other than `OSC3`/`ENV3` is **write-only on real
hardware** -- reading `$00`-`$18` (or `POTX`/`POTY` with no paddle
attached) returns indeterminate bus noise on a real chip. This
implementation returns `$FF` for all of them, a common, harmless
simplification (nothing in this project reads its own SID registers back
expecting the written value).

## Oscillator: a 24-bit phase accumulator drives all four waveforms

Every voice has a 24-bit accumulator that adds its 16-bit frequency value
to itself every PHI2 cycle (wrapping at 24 bits) -- the higher the
frequency value, the faster it wraps, i.e. the higher the pitch. All four
waveforms are different readings of the same accumulator:

- **Sawtooth**: the top 12 bits of the accumulator, directly -- a linear
  ramp that resets to 0 every wrap.
- **Triangle**: the top 12 bits of `(accumulator << 1)`, XORed with all-1s
  whenever the accumulator's top bit is set (or, if ring modulation is on,
  whenever *this voice's* top bit XOR the *modulating voice's* top bit is
  set instead -- see "Ring modulation" below) -- folds the ramp into an
  up/down triangle.
- **Pulse**: `$FFF` (full on) while the top 12 bits of the accumulator are
  `>=` the 12-bit pulse width register, else `$000`.
- **Noise**: a 23-bit LFSR, shifted once per accumulator whenever bit 19
  transitions 0->1, feeding taps 22 and 17 (XORed) back into bit 0; 8 bits
  read from fixed LFSR positions form the noise output. **Approximation,
  not bit-exact**: real hardware's noise generator (and its well-known
  interactions with combined waveforms) is one of the most intricate,
  carefully reverse-engineered parts of reSID; this is a plausible LFSR
  matching the commonly-published structure, not independently verified
  against real silicon.
- **Combined waveforms** (more than one waveform bit set at once): real
  hardware does something non-linear and chip-revision-dependent here.
  This implementation just ANDs the individual waveform outputs together
  bit-by-bit -- the standard simplification most non-reSID-grade
  emulators use, not a claim of accuracy.

`TEST` (control bit 3) forces the accumulator to stay at 0 (used by real
software to reset phase before a controlled release). `GATE` (bit 0)
doesn't affect the oscillator at all -- only the envelope (below).

## Hard sync and ring modulation

Both couple a voice to the *previous* voice in the circular order
1←3, 2←1, 3←2 (voice 1's source is voice 3, matching real hardware's
wiring):

- **SYNC** (control bit 1): this voice's accumulator is forcibly reset to
  0 the instant the source voice's accumulator wraps (its top bit
  transitions 1->0, i.e. it crosses zero) -- the classic hard-sync effect.
- **RING MOD** (control bit 2): only affects this voice's *triangle*
  output -- the fold direction (see above) is driven by this voice's top
  bit XORed with the source voice's top bit, instead of just this voice's
  own top bit. Selecting ring mod without triangle selected has no
  audible effect, matching real hardware.

## ADSR envelope

Attack/Decay/Sustain/Release are each a 4-bit register field. Attack and
Decay/Release rates index a lookup table of real datasheet-published
times (fetched from the actual MOS 6581 datasheet, not reproduced from
memory unchecked -- see the table below), quoted "based on a 1.0MHz Ø2
clock" and scaled here to this project's actual PAL clock
(`vic_ii.PAL_CLOCK_HZ`, 985,248 Hz -- close enough to 1MHz that the
~1.5% difference barely matters, but it's applied anyway for
correctness). Sustain is a 4-bit level, mapped to an 8-bit target the
standard way (`sustain | (sustain << 4)`, giving 16 evenly-spaced levels
from 0 to 255).

| Rate index | Attack | Decay/Release |
|---|---|---|
| 0 | 2ms | 6ms |
| 1 | 8ms | 24ms |
| 2 | 16ms | 48ms |
| 3 | 24ms | 72ms |
| 4 | 38ms | 114ms |
| 5 | 56ms | 168ms |
| 6 | 68ms | 204ms |
| 7 | 80ms | 240ms |
| 8 | 100ms | 300ms |
| 9 | 250ms | 750ms |
| 10 | 500ms | 1.5s |
| 11 | 800ms | 2.4s |
| 12 | 1s | 3s |
| 13 | 3s | 9s |
| 14 | 5s | 15s |
| 15 | 8s | 24s |

State machine, triggered by `GATE`: a rising edge starts (or continues --
re-triggering while already attacking does **not** reset to 0, matching
real hardware) the **attack** phase, stepping the 8-bit envelope level up
by 1 every attack-rate period until it reaches 255, then automatically
switching to **decay**, stepping down toward the sustain level, then
holding at **sustain**. A falling edge switches to **release** from
whatever the current level is, stepping down toward 0 regardless of
phase.

**Approximation**: real decay/release isn't linear -- the chip slows the
step rate as the level drops, approximating an exponential curve, using
an widely-published (though not independently re-verified against a
physical chip in this session) zone table: divide the nominal rate
period by the envelope level's zone -- `255`-`93`: ×1, `92`-`54`: ×2,
`53`-`26`: ×4, `25`-`14`: ×8, `13`-`6`: ×16, `5`-`0`: ×30. Attack has no
such zone table (it's linear).

## Filter: a simple digital state-variable filter, not reSID's transistor model

`$17`/`$18` select which voices feed the filter, which of low-pass/
band-pass/high-pass outputs get mixed into the final signal (any
combination -- e.g. low+high with band-pass excluded approximates a
notch), and an 11-bit cutoff plus 4-bit resonance. This implementation
runs a classic digital state-variable filter (the Chamberlin topology --
generic, well-known DSP, not reSID-derived) over the sum of the routed
voices, once per output sample. **This is a plain digital approximation,
not a model of the real 6581/8580's genuinely analog, non-linear,
unit-to-unit-variable filter** -- exactly the gap the roadmap flagged as
acceptable to defer. The cutoff-register-to-Hz mapping is a simple linear
approximation (no two real chips agree closely enough to make a single
"correct" curve meaningful without hardware to calibrate against).

## Known gaps

- **Filter is a simple digital approximation**, not remotely reSID-grade
  (see above). Revisit if specific real software's sound is noticeably
  off and the filter is why.
- **Noise generator's LFSR structure is plausible but not independently
  verified bit-exact.** Combined-waveform behavior (including the real
  chip's noise-generator "lockup" quirk when combined with other
  waveforms) isn't modeled at all.
- **No paddle input** (`$19`/`$1A` just read `$FF`) and no external audio
  input to the filter (`$17` bit 3 is stored but does nothing) -- neither
  exists in this project.
- **Nothing plays real audio yet.** `Sid.tick(cycles)` advances oscillator
  and envelope state exactly like `CIA6526.tick`/`VicII.tick`, and
  `output_sample()` reads the current instantaneous mixed/filtered level
  -- but nothing yet calls these from a real running loop or feeds the
  result to an actual audio device. That's the same "no real machine yet"
  gap noted in `docs/cia.md` and `docs/vic-ii.md`, plus the `peripherals/`
  layer discussed for later (screen/keyboard/disk/cartridge bridges) is
  the natural home for an audio output bridge too.
