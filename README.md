# c64-emulator-python

A Python emulator for the Commodore 64: the real memory map (with bank
switching), the VIC-II video chip, the SID sound chip, both CIA I/O
chips, cartridge and disk support, and real screen/keyboard/audio/
joystick I/O — enough to boot the real BASIC/KERNAL and run real C64
software. See [CLAUDE.md](CLAUDE.md) for the full goals, decisions, and
phased status; each custom chip/subsystem has its own doc in
[docs/](docs/) (`cia.md`, `vic-ii.md`, `sid.md`, `machine.md`,
`cartridge.md`, `disk.md`).

The emulation core (`src/c6502/`, `src/c64/`) has zero runtime
dependencies. Real screen/keyboard/audio I/O (`src/peripherals/`) needs
this project's `peripherals` extra (`pygame` + `sounddevice`).

## Quickstart

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,peripherals]"
scripts/stage_roms.sh          # stages your own local C64 ROMs -- see below
.venv/bin/python scripts/run_c64.py
```

**ROMs are never fetched or vendored by this project** (their copyright
status is genuinely unresolved -- see `docs/roadmap.md`'s Phase 1).
`scripts/stage_roms.sh` only copies ROMs you already have locally (e.g.
already installed by VICE) into this repo's gitignored `roms/c64/`.

**PyPy is meaningfully faster** (6.7x-8.8x across real benchmarks --
see `docs/machine.md`'s Performance section) and fully supported: the
same commands work with `pypy3`/`.venv-pypy` in place of `python3`/
`.venv`. Recommended for anything with audio enabled.

## Running the emulator

`scripts/run_c64.py` boots the staged ROMs into a real window with
keyboard, joystick, and audio all live. Every option below can be
combined with any other.

**Plain boot** — real KERNAL/BASIC, straight to the `READY.` prompt:
```
scripts/run_c64.py
```
A disk is *always* mounted on device 8, even with no `--disk` given —
see "Disk" below.

**Cartridge** — load a real `.crt` file, like plugging one into the
expansion port:
```
scripts/run_c64.py --cartridge cartridge-slot/some_game.crt
```
Generic/type-0 and Ultimax-mode cartridges only (no bank-switching
hardware types) — see `docs/cartridge.md`. `cartridge-slot/` is a
suggested (gitignored) place to keep `.crt` files; it's never
auto-scanned, so a plain run stays cartridge-free even with files sitting
in it. `scripts/wrap_raw_cartridge.py` can wrap a raw/headerless ROM dump
into a proper `.crt` if that's what you have instead.

**Typing a program automatically** — reliable, frame-timed input instead
of live keystrokes (see `src/peripherals/auto_type.py` for why live
typing alone isn't rock solid):
```
scripts/run_c64.py --type-file examples/sound_test.bas
```
Or paste with **Ctrl+V** at any point once you're sitting at a prompt
(reads the real system clipboard).

**Disk** — KERNAL-trap disk emulation (`LOAD`/`SAVE`/`LOAD"$",8`) against
real `.d64` images — see `docs/disk.md` for the format and the (large)
class of software this can't run yet (anything with a custom
"fastloader"). With no `--disk` at all, device 8 still gets a real disk
that *persists* across runs, at the gitignored `disk-drive/disk8.d64`
(seeded blank the first time it's needed):
```
scripts/run_c64.py
```
To use a disk at a path of your own choosing (or more than one drive —
see below), name a real file — created blank automatically if it doesn't
exist yet, and saved back to it when the emulator closes, same as the
default:
```
scripts/run_c64.py --disk 8:mydisk.d64
```
Repeat `--disk` for more drives (real 1541s are jumper-configurable the
same way):
```
scripts/run_c64.py --disk 8:games.d64 --disk 9:data.d64
```

**Joystick** — the numeric keypad drives one C64 joystick port at a
time: `8`/`2`/`4`/`6` for up/down/left/right, `7`/`9`/`1`/`3` for
diagonals, `0` for fire. Defaults to port 2 (the real-world default for
single-joystick software); **F2** switches which port it drives. No flag
needed — always live. The numpad's `*` key is untouched by this and
types the real C64 `*` (its own dedicated key on real hardware, with no
equivalent on a standard PC keyboard — deliberately not `Shift+8`, which
stays `(` as on real hardware).

**Audio** — on by default (`sounddevice`/PortAudio, not `pygame.mixer` —
see `src/peripherals/audio.py` for why); `--no-audio` skips SID ticking
entirely (screen/keyboard/disk all still work):
```
scripts/run_c64.py --no-audio
```

**Combining everything** — a cartridge, a persistent disk, and a
typed-in program all at once:
```
scripts/run_c64.py --cartridge cartridge-slot/some_game.crt \
    --disk 8:mydisk.d64 --type-file examples/sprite_test.bas
```

If the CPU ever hits a JAM/KIL opcode or one of the handful of still-
unimplemented chip-unstable illegal opcodes (see
`docs/6502-reference.md`), that's a real, documented failure mode — real
hardware genuinely halts there too. The emulator degrades gracefully: a
message prints, the window stays open showing the last frame, and you
close it to exit.

## Other scripts

- `scripts/render_frame.py` — boots the staged ROMs and writes a PNG of
  the VIC-II's screen output (no window/keyboard/audio; useful for quick,
  scriptable checks).
- `scripts/render_audio.py` — plays a test tone through the real SID
  stack and writes a WAV file.
- `scripts/sid_digi_playback_diagnostic.py` — renders SID
  "digi-playback" (volume-register sample-through) scenarios to WAV —
  see `docs/sid.md`'s Known Gaps.
- `scripts/wrap_raw_cartridge.py` — wraps a raw/headerless ROM chip dump
  into a proper `.crt` (`--ultimax` for Ultimax-mode headers).

## Running tests

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

To also re-validate the ported CPU core against Klaus Dormann's suite
(not vendored — fetched on demand, ~80s):
```
scripts/fetch_dormann_tests.sh
.venv/bin/pytest -m slow
```

`src/peripherals/`'s own tests need the `peripherals` extra (`pip install
-e ".[dev,peripherals]"`); they're skipped cleanly otherwise.
