#!/usr/bin/env bash
# Stages Commodore ROM images (kernal/basic/chargen) into this repo's
# gitignored roms/c64/ directory, copied from ROMs the user already has
# locally (e.g. dropped in by installing VICE). Never downloads anything:
# their copyright status is unverified (see docs/roadmap.md's Phase 1 and
# docs/testing-strategy.md's license discipline section), so acquiring your
# own legitimate copy -- a real C64 dump, or whatever VICE already put on
# this machine -- is your responsibility, not this script's.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="$REPO_ROOT/roms/c64"

CANDIDATE_DIRS=(
    "${1:-}"
    "$HOME/.local/share/vice/C64"
    "/usr/lib/vice/C64"
    "/usr/share/vice/C64"
)

# MD5s of the most common revision of each ROM (kernal 901227-03, basic
# 901226-01, chargen 901225-01) -- known-good references to catch this
# script silently staging an unexpected file (wrong revision, truncated
# download, bit rot), not a whitelist. Other real revisions exist (PAL vs
# NTSC, C64GS, SX-64...) and are legitimate; an unrecognized hash is a
# prompt to eyeball the file yourself, not proof it's wrong.
declare -A KNOWN_MD5=(
    [kernal]="39065497630802346bce17963f13c092"
    [basic]="57af4ae21d4b705c2991d98ed5c1f7b8"
    [chargen]="12a4202f5331d45af846af6c58fba946"
)

find_rom() {
    local basename="$1" dir match
    # Exact match (VICE's own default filename) wins, tried across every
    # candidate dir first -- an exact name means "the standard ROM this
    # install boots with", which beats guessing among revision variants.
    for dir in "${CANDIDATE_DIRS[@]}"; do
        [[ -n "$dir" && -d "$dir" ]] || continue
        if [[ -f "$dir/$basename" ]]; then
            echo "$dir/$basename"
            return 0
        fi
    done
    # Only if no dir has an exact match, fall back to the revision-suffixed
    # names VICE's full ROM pack uses (e.g. kernal-901227-03.bin), taking
    # the lowest-sorting match -- a guess, since nothing here says which
    # revision is "standard".
    for dir in "${CANDIDATE_DIRS[@]}"; do
        [[ -n "$dir" && -d "$dir" ]] || continue
        match="$(find "$dir" -maxdepth 1 -iname "${basename}-*.bin" 2>/dev/null | sort | head -n1)"
        if [[ -n "$match" ]]; then
            echo "$match"
            return 0
        fi
    done
    return 1
}

mkdir -p "$DEST_DIR"

missing=()
for rom in kernal basic chargen; do
    src="$(find_rom "$rom" || true)"
    if [[ -z "$src" ]]; then
        missing+=("$rom")
        continue
    fi
    cp "$src" "$DEST_DIR/$rom"
    actual_md5="$(md5sum "$DEST_DIR/$rom" | cut -d' ' -f1)"
    if [[ "$actual_md5" == "${KNOWN_MD5[$rom]}" ]]; then
        echo "staged $rom <- $src (md5 matches known-common revision)"
    else
        echo "staged $rom <- $src"
        echo "  warning: md5 $actual_md5 doesn't match the common revision" \
             "(${KNOWN_MD5[$rom]}) -- could be a legitimate different" \
             "revision (PAL/NTSC, C64GS, SX-64...), or could be the wrong" \
             "file. Worth a manual check." >&2
    fi
done

if (( ${#missing[@]} > 0 )); then
    echo
    echo "Could not find: ${missing[*]}" >&2
    echo "Looked in: ${CANDIDATE_DIRS[*]}" >&2
    echo "Point this script at your own ROM directory instead:" >&2
    echo "  scripts/stage_roms.sh /path/to/your/roms" >&2
    exit 1
fi

echo
echo "ROMs staged in $DEST_DIR (gitignored -- never committed)."
