#!/usr/bin/env bash
# Single source of truth for the SDK version. Every file that embeds the
# version is listed here; CI runs check-version.sh to prove they agree.
#   scripts/set-version.sh 0.4.0
set -euo pipefail
cd "$(dirname "$0")/.."
NEW="${1:?usage: set-version.sh X.Y.Z}"
[[ "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "not a semver: $NEW" >&2; exit 1; }
CUR=$(sed -n 's/^  "version": "\(.*\)",$/\1/p' js/package.json)
[ -n "$CUR" ] || { echo "cannot read current version from js/package.json" >&2; exit 1; }
esc() { printf '%s' "$1" | sed 's/\./\\./g'; }
C=$(esc "$CUR")
files=(
  js/package.json js/index.js js/README.md
  python/pyproject.toml python/src/anva/__init__.py python/src/anva/client.py python/README.md
  go/anva.go go/README.md README.md
)
for f in "${files[@]}"; do
  sed -i '' -e "s/anva-js\/$C/anva-js\/$NEW/g" \
            -e "s/anva-python\/$C/anva-python\/$NEW/g" \
            -e "s/anva-go\/$C/anva-go\/$NEW/g" \
            -e "s/\"version\": \"$C\"/\"version\": \"$NEW\"/" \
            -e "s/^version = \"$C\"/version = \"$NEW\"/" \
            -e "s/__version__ = \"$C\"/__version__ = \"$NEW\"/" \
            -e "s/anva-sdk@$C/anva-sdk@$NEW/g" \
            -e "s/anva\[ws\]==$C/anva[ws]==$NEW/g" \
            -e "s/go@v$C/go@v$NEW/g" \
            -e "s/\*\*$C\*\*/**$NEW**/g" "$f"
done
echo "version $CUR -> $NEW"
scripts/check-version.sh
