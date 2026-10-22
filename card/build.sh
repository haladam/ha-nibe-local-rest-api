#!/bin/sh
# Concatenate the parts into card/nibe-plant-card.js.
# The version is the first argument, or else the one in the integration's manifest.json.
set -e
cd "$(dirname "$0")"
MANIFEST=../custom_components/nibe_local_api/manifest.json
VERSION="${1:-$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$MANIFEST")}"
[ -n "$VERSION" ] || { echo "no version found" >&2; exit 1; }
cat src/00-header.js src/01-helpers.js src/02-plant.js src/03-primitives.js src/04-components.js src/05-styles.js src/06-scene.js src/07-card.js \
  | sed "s/__VERSION__/$VERSION/" > nibe-plant-card.js
node --check nibe-plant-card.js
echo "built card/nibe-plant-card.js for version $VERSION ($(wc -l < nibe-plant-card.js) lines)"
