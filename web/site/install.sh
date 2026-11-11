#!/bin/sh
# Installs the scriptt harness in the current folder: 5 files in .scriptt/, then 2 hooks and 1 skill in .claude/.
# Every file is downloaded first, then moved into place, so a failed download changes nothing. An existing
# .scriptt/world.py is yours: it is not replaced.
set -eu
mkdir -p .scriptt
new="$(mktemp -d .scriptt/.new.XXXXXX)"
trap 'rm -rf "$new"' EXIT
for file in harness.py agree.py scriptt16.py SKILL.md world.py; do
  curl -fsSL "https://scriptt.ai/$file" -o "$new/$file"
done
for file in harness.py agree.py scriptt16.py SKILL.md; do mv "$new/$file" ".scriptt/$file"; done
[ -e .scriptt/world.py ] || mv "$new/world.py" .scriptt/world.py
"${SCRIPTT_PYTHON:-python3.14}" .scriptt/harness.py install
