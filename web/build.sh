#!/bin/sh
# Builds the scriptt.ai site into web/public: the page and the board from web/site, the roadmap, and the files that
# install.sh downloads (the board's demo also runs harness.py, agree.py and scriptt16.py in the browser).
# Run from the repository root: sh web/build.sh. Then deploy: (cd web && npx cf deploy).
set -eu
mkdir -p web/public
rsync -a --delete web/site/ web/public/
cp scriptt/harness.py scriptt/world.py scriptt/SKILL.md next/agree.py next/scriptt16.py web/public/
cp ROADMAP.md web/public/roadmap.md
echo "built web/public"
