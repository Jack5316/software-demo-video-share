#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p out/scenes

node -e "const p=require('./src/scenePlan.json'); for (const s of p.scenes) console.log(s.id)" |
while IFS= read -r scene; do
  [[ -n "$scene" ]] || continue
  ./node_modules/.bin/remotion render src/index.ts "$scene" "out/scenes/${scene}.mp4" \
    --codec=h264 --crf=18 --log=error --concurrency=4
done
