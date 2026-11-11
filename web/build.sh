#!/bin/sh
# Builds the scriptt.ai site into web/public: the page in web/site, and the 3 files that install.sh downloads.
# web/site/versions and web/site/audit.js are working files of the UI builds: they are not part of the site.
# Run from the repository root: sh web/build.sh. Then deploy: (cd web && npx cf deploy).
set -eu
mkdir -p web/public
rsync -a --delete --exclude versions --exclude audit.js --exclude audits web/site/ web/public/
cp scriptt/harness.py scriptt/world.py scriptt/SKILL.md web/public/
echo "built web/public"
