#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p out

ffmpeg_bin="${SOFTWARE_DEMO_FFMPEG:-}"
if [[ -z "$ffmpeg_bin" && -x /opt/homebrew/bin/ffmpeg ]]; then
  ffmpeg_bin=/opt/homebrew/bin/ffmpeg
fi
if [[ -z "$ffmpeg_bin" ]]; then
  ffmpeg_bin="$(command -v ffmpeg)"
fi

list_file=out/concat.txt
raw_file=out/concat-raw.mp4
audio_rate="$(node -e "const p=require('./src/scenePlan.json'); console.log(p.audioSampleRate)")"
output_filename="$(node -e "const p=require('./src/scenePlan.json'); console.log(p.outputFilename)")"
: > "$list_file"
node -e "const p=require('./src/scenePlan.json'); for (const s of p.scenes) console.log(s.id)" |
while IFS= read -r scene; do
  [[ -n "$scene" ]] || continue
  printf "file '%s'\n" "$(pwd)/out/scenes/${scene}.mp4" >> "$list_file"
done

"$ffmpeg_bin" -y -v error -f concat -safe 0 -i "$list_file" -c copy "$raw_file"
"$ffmpeg_bin" -y -v error -i "$raw_file" -map 0:v:0 -map 0:a:0 \
  -c:v copy -af "loudnorm=I=-16:TP=-1.5:LRA=7,aresample=${audio_rate}" \
  -c:a aac -b:a 192k -ar "$audio_rate" -movflags +faststart "out/${output_filename}"
