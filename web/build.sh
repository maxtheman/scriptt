#!/bin/sh
# Build the scriptt.ai site into web/public: the landing page at / and the docs site at /docs/.
# Run from worldapi/: sh web/build.sh. Then deploy from web/: npx cf deploy.
set -eu
uv run python -m docs.build
uv run --group docs mkdocs build --strict -f docs/mkdocs.yml
mkdir -p web/public/docs
rsync -a --delete web/landing/ web/public/ --exclude docs
rsync -a --delete site/ web/public/docs/
