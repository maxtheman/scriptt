#!/bin/sh
# Builds the scriptt.ai site into web/public: the one page in web/site and anything beside it.
# Run from the repository root: sh web/build.sh. Deploying is a separate, manual step.
set -eu
mkdir -p web/public
rsync -a --delete web/site/ web/public/
echo "built web/public"
