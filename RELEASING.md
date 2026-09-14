# Releasing the SDKs

1. Add entries under `## Unreleased` in `CHANGELOG.md` as you work. Every
   user-visible change gets a bullet; breaking changes say **Breaking:**.
2. Cut a release: `scripts/set-version.sh X.Y.Z` rewrites every embedded
   version (package.json, pyproject, `__version__`, three User-Agents, READMEs)
   and then runs `scripts/check-version.sh`.
3. Rename `## Unreleased` to `## X.Y.Z — YYYY-MM-DD` (leave an empty
   `## Unreleased` above it). `check-version.sh` fails if the top release
   does not match the package version.
4. Run tests: `cd js && npm test`, `cd python && python -m pytest`,
   `cd go && go test ./...`.
5. Commit, tag `vX.Y.Z` and `go/vX.Y.Z` (the Go module lives in a subdirectory,
   so its tag must carry the `go/` prefix), push tags.
6. Publish: `cd js && npm publish`, `cd python && rm -rf dist && python -m build
   && python -m twine upload dist/*`. Go is served from the tag.
7. Update the install lines in the server docs if the SDK major changed.

Never publish from a tree where `scripts/check-version.sh` fails.
