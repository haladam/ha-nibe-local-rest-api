#!/usr/bin/env bash
# Prepare a release:  ./scripts/release.sh 0.9.11
#
# 1. checks that the working tree is clean and CHANGELOG.md has a "## 0.9.11" section
# 2. sets the version in manifest.json, rebuilds the card from card/src and copies it into the integration
# 3. runs all tests
# 4. commits ("Release 0.9.11") and tags v0.9.11
#
# Nothing is pushed. Push when you are happy:   git push && git push --tags
# The tag starts the Release workflow, which creates the GitHub release HACS offers as the update.
set -euo pipefail
cd "$(dirname "$0")/.."

version=${1:-}
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "usage: $0 <major.minor.patch>" >&2; exit 1; }
manifest=custom_components/nibe_local_api/manifest.json

[ -z "$(git status --porcelain)" ] || { echo "the working tree is not clean: commit or stash first" >&2; exit 1; }
git rev-parse -q --verify "refs/tags/v$version" >/dev/null && { echo "tag v$version exists already" >&2; exit 1; }
grep -q "^## $version\b" CHANGELOG.md || { echo "CHANGELOG.md has no '## $version' section: write the notes first" >&2; exit 1; }

python3 - "$manifest" "$version" <<'PY'
import json, sys
path, version = sys.argv[1:]
manifest = json.load(open(path, encoding="utf-8"))
manifest["version"] = version
open(path, "w", encoding="utf-8").write(json.dumps(manifest, indent=2) + "\n")
PY

./scripts/sync_card.sh
./scripts/run_tests.sh

git add -A
git commit -q -m "Release $version"
git tag -a "v$version" -m "Release $version"
echo
echo "Release $version is committed and tagged. To publish it:"
echo "  git push && git push --tags"
