# c64-emulator-python

A Python emulator for the Commodore 64. See [CLAUDE.md](CLAUDE.md) for
the full goals, what's already built, and the phased plan.

## Status

Just getting started: the 6502 CPU core and assembler are ported over
from a sibling project ([c-compiler-6502](https://github.com/michaelkemp/c-compiler-6502))
where they were built and validated against Klaus Dormann's functional
test suite. Nothing C64-specific (VIC-II, SID, CIA, the real memory map)
exists yet — see [docs/roadmap.md](docs/roadmap.md).

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
