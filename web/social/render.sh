#!/bin/sh
# Renders the images that link previews and browsers use, into web/site:
#   og.png (1200x630) from web/social/card.html with headless Chrome, for Open Graph and Twitter cards;
#   wordmark-dark.png and wordmark-light.png (transparent, for the README) from web/social/wordmark.html;
#   apple-touch-icon.png (180x180) and favicon-32.png from web/site/favicon.svg with rsvg-convert.
# Run from the repository root: sh web/social/render.sh. Commit the images; web/build.sh ships them.
set -eu
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=1200,630 --virtual-time-budget=5000 \
  --screenshot="$PWD/web/site/og.png" "file://$PWD/web/social/card.html"
for scheme in dark light; do
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=640,160 --default-background-color=00000000 --virtual-time-budget=5000 \
    --screenshot="$PWD/web/site/wordmark-$scheme.png" "file://$PWD/web/social/wordmark.html#$scheme"
done
rsvg-convert -w 180 -h 180 web/site/favicon.svg -o web/site/apple-touch-icon.png
rsvg-convert -w 32 -h 32 web/site/favicon.svg -o web/site/favicon-32.png
echo "rendered og.png, wordmark-dark.png, wordmark-light.png, apple-touch-icon.png, favicon-32.png"
