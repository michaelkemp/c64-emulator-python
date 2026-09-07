#!/usr/bin/env bash
# Downloads Klaus Dormann's pre-assembled 6502 functional test binary into a
# gitignored fixtures directory. Not vendored in this repo -- it's GPLv3,
# see docs/testing-strategy.md for why we fetch it on demand instead.
set -euo pipefail

REPO_RAW="https://raw.githubusercontent.com/Klaus2m5/6502_65C02_functional_tests/master"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="$REPO_ROOT/tests/emulator/fixtures/dormann"

mkdir -p "$DEST_DIR"
echo "Downloading Klaus Dormann's 6502 functional test binary (GPLv3, not vendored in this repo)..."
curl -sL -o "$DEST_DIR/6502_functional_test.bin" "$REPO_RAW/bin_files/6502_functional_test.bin"
echo "Saved to $DEST_DIR/6502_functional_test.bin"
echo "Run 'pytest -m slow' to validate the CPU core against it."
