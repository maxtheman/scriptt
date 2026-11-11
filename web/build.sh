#!/bin/sh
# Builds the scriptt.ai site into web/public: the page in web/site, and the 5 files that install.sh downloads.
# The engine (agree.py, scriptt16.py) has 1 copy, in next/; it ships beside harness.py.
# Run from the repository root: sh web/build.sh. Then deploy: (cd web && npx cf deploy).
set -eu
mkdir -p web/public
rsync -a --delete web/site/ web/public/
cp scriptt/harness.py scriptt/world.py scriptt/SKILL.md next/agree.py next/scriptt16.py web/public/
echo "built web/public"
