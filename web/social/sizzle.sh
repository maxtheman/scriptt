#!/bin/sh
# Renders web/site/sizzle.gif (and sizzle.mp4) from web/social/sizzle.html: headless Chrome captures each frame at its
# time (#t=...), then ffmpeg encodes them with one palette for the whole GIF.
# Run from the repository root: sh web/social/sizzle.sh. Needs Google Chrome and ffmpeg.
set -eu
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
FPS=15
SECONDS_LONG=10
frames="web/social/.frames"
rm -rf "$frames" && mkdir -p "$frames"
n=0
total=$((FPS * SECONDS_LONG))
while [ "$n" -lt "$total" ]; do
  t=$(awk "BEGIN { printf \"%.3f\", $n / $FPS }")
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=1200,675 --virtual-time-budget=4000 \
    --screenshot="$PWD/$frames/$(printf '%04d' "$n").png" "file://$PWD/web/social/sizzle.html#t=$t" >/dev/null 2>&1
  n=$((n + 1))
done
ffmpeg -loglevel error -y -framerate "$FPS" -i "$frames/%04d.png" -vf "scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" -loop 0 web/site/sizzle.gif
ffmpeg -loglevel error -y -framerate "$FPS" -i "$frames/%04d.png" -vf scale=1200:-2 -c:v libx264 -pix_fmt yuv420p -crf 20 web/site/sizzle.mp4
rm -r "$frames"
ls -l web/site/sizzle.gif web/site/sizzle.mp4
