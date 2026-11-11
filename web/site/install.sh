#!/bin/sh
# Installs the scriptt harness in the current folder: 5 files in .scriptt/, then 2 hooks and 1 skill in .claude/.
# An existing .scriptt/world.py is yours: it is not replaced.
set -eu
mkdir -p .scriptt
for file in harness.py agree.py scriptt16.py SKILL.md world.py; do
  if [ "$file" != world.py ] || [ ! -e .scriptt/world.py ]; then curl -fsSL "https://scriptt.ai/$file" -o ".scriptt/$file"; fi
done
"${SCRIPTT_PYTHON:-python3.14}" .scriptt/harness.py install
