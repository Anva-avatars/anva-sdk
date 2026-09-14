#!/usr/bin/env bash
# Fails unless every embedded version string agrees with js/package.json and
# the top released entry of CHANGELOG.md matches it.
set -euo pipefail
cd "$(dirname "$0")/.."
V=$(sed -n 's/^  "version": "\(.*\)",$/\1/p' js/package.json)
fail=0
chk() { grep -q -- "$2" "$1" || { echo "MISMATCH: $1 lacks '$2'" >&2; fail=1; }; }
chk js/index.js "anva-js/$V"
chk python/pyproject.toml "version = \"$V\""
chk python/src/anva/__init__.py "__version__ = \"$V\""
chk python/src/anva/client.py "anva-python/$V"
chk go/anva.go "anva-go/$V"
chk README.md "anva-sdk@$V"
chk README.md "anva\[ws\]==$V"
chk README.md "go@v$V"
chk js/README.md "anva-sdk@$V"
chk python/README.md "anva\[ws\]==$V"
chk go/README.md "go@v$V"
top=$(grep -m1 -E '^## [0-9]+\.[0-9]+\.[0-9]+' CHANGELOG.md | sed -E 's/^## ([0-9.]+).*/\1/')
[ "$top" = "$V" ] || { echo "MISMATCH: CHANGELOG top release is '$top', package version is '$V'" >&2; fail=1; }
grep -qE '^## Unreleased\s*$' CHANGELOG.md && { echo "CHANGELOG still has an Unreleased section; move it under $V or leave it empty with a date" >&2; }
[ $fail = 0 ] && echo "version $V consistent across SDKs and CHANGELOG"
exit $fail
