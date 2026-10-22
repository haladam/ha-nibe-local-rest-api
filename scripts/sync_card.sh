#!/bin/sh
# Build the card from card/src and copy it into the integration (the copy HACS ships).
set -e
cd "$(dirname "$0")/.."
./card/build.sh
cp card/nibe-plant-card.js custom_components/nibe_local_api/frontend/nibe-plant-card.js
echo "copied into custom_components/nibe_local_api/frontend/"
