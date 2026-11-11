#!/bin/sh
# Freezes the current board as web/site/versions/vNN/ (index.html, board.js, model.js, audit.js), reading engine/ and vendor/ from the site.
# The frozen board opens at that version's layout (default ?v=NN). Run from the repository root: sh web/mkver.sh 13
set -eu
n="$1"; d="web/site/versions/v$n"
mkdir -p "$d"
cp web/site/model.js web/site/audit.js "$d/"
sed -e "s#fetch(\"engine/#fetch(\"../../engine/#g" -e "s#get(\"v\") ?? 15#get(\"v\") ?? $n#" web/site/board.js > "$d/board.js"
sed -e 's#src="vendor/#src="../../vendor/#' web/site/index.html > "$d/index.html"
echo "frozen $d (open /versions/v$n/index.html?audit)"
