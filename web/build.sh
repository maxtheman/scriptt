#!/bin/sh
# Builds the scriptt.ai site into web/public: the page in web/site, and the 3 files that install.sh downloads.
# Run from the repository root: sh web/build.sh. Then deploy: (cd web && npx cf deploy).
set -eu
mkdir -p web/public
rsync -a --delete web/site/ web/public/
cp scriptt/harness.py scriptt/world.py scriptt/SKILL.md web/public/
echo "built web/public"
