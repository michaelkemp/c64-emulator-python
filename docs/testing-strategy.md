# Testing strategy

## CPU core + assembler (ported, Phase 0)

Both came over from `c-compiler-6502` with their full test suites intact
(one test adapted — see `docs/roadmap.md`'s Phase 0 notes). Two layers,
same as the source repo:

1. **Klaus Dormann's 6502 functional test suite** — GPLv3-licensed,
   fetched on demand rather than vendored: run
   `scripts/fetch_dormann_tests.sh` once, then `pytest -m slow`. Traps at
   `$3469` on success; any other trap address is a specific failing test,
   identifiable by fetching the suite's own `.lst` listing. This is the
   real correctness gate for the CPU core — it already passed in the
   source repo, and re-running it here after the port is the first thing
   worth doing to prove nothing broke in transit.
2. **Hand-written unit tests** (`tests/emulator/`, `tests/asm/`) — fast,
   pinpoint exactly which instruction/addressing-mode/assembler concern
   broke, rather than just "the functional suite failed somewhere."

## C64-specific chips (not started)

No strategy written yet since nothing's implemented — write this section
as each phase in `docs/roadmap.md` actually gets built, following the
same shape as above: a real, external, independently-authored correctness
gate (real ROM software booting and behaving correctly; a demo/test
program known to depend on exact VIC-II or SID behavior) plus fast
hand-written unit tests for pinpointing regressions.

## License discipline (carried over as a hard rule, not just a suggestion)

The source repo hit real, corrected mistakes about this — see its
`docs/testing-strategy.md` for the full history (an early, wrong "public
domain" claim about Klaus Dormann's suite; a claimed-but-unverifiable
"2-clause BSD" license on `msbasic` with no actual `LICENSE` file backing
it up). The rule that came out of that: **never vendor third-party
content into this repo's git history without an actually-verified
license** — read the real license file/text yourself rather than trusting
a README's claim, and default to fetch-on-demand (gitignored, a script in
`scripts/`) when in doubt. This applies directly to:

- **Commodore's ROMs** — see `docs/roadmap.md`'s Phase 1 (ROM licensing
  research is a prerequisite to writing any chip code, not an
  afterthought).
- **reSID** (GPL) — fine to read for understanding the SID's analog
  filter model; don't copy its code into this repo.
- **VICE** (GPL) — fine to run/read as a reference implementation to
  check our own behavior against; same rule.
