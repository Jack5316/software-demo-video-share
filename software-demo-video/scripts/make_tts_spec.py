#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import load_edit_spec


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert an edit spec into minimax-tts cue format.")
    parser.add_argument("spec", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--slug", default=None)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--silence-gap-ms", type=int, default=180)
    args = parser.parse_args()

    spec = load_edit_spec(args.spec.resolve())
    slug = args.slug or Path(spec["output"]["filename"]).stem
    result = {
        "slug": slug,
        "speed": args.speed,
        "silence_gap_ms": args.silence_gap_ms,
        "cues": [{"id": scene["id"], "text": scene["narration"]} for scene in spec["scenes"]],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "slug": slug, "cues": len(result["cues"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
