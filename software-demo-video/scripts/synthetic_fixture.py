#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from _common import resolve_ffmpeg


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate private-free synthetic media and a minimal edit spec for smoke tests.")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    tools = resolve_ffmpeg()
    ffmpeg = tools["ffmpeg"]
    encoder = tools["encoder"]
    video_args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p"] if encoder == "libx264" else ["-c:v", "h264_videotoolbox", "-b:v", "3M", "-pix_fmt", "yuv420p"]

    raw_dir = output / "raw clips"
    raw_dir.mkdir(exist_ok=True)
    first = raw_dir / "导航 测试.mp4"
    second = raw_dir / "结果 test.mp4"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-t", "2.5", *video_args, str(first)], check=True)
    subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x1f6feb:size=1280x720:rate=30", "-t", "2.5", *video_args, str(second)], check=True)
    audio = output / "combined narration.mp3"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=32000", "-t", "4", "-c:a", "libmp3lame", "-b:a", "128k", str(audio)], check=True)

    cues = {
        "slug": "synthetic-demo",
        "duration": 4.0,
        "cues": [
            {"id": "scene-01", "start": 0.0, "end": 2.0, "text": "打开测试页面。"},
            {"id": "scene-02", "start": 2.0, "end": 4.0, "text": "查看测试结果。"}
        ]
    }
    (output / "cues.json").write_text(json.dumps(cues, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    spec = {
        "version": "software-demo-video.edit-spec/v1",
        "output": {"width": 1280, "height": 720, "fps": 30, "audio_sample_rate": 32000, "filename": "synthetic-demo.mp4"},
        "source_provenance": [{"id": "synthetic", "label": "Generated test pattern", "level": "local-user-source", "checked_at": "2026-08-27"}],
        "scenes": [
            {
                "id": "scene-01", "title": "Open", "narration": "打开测试页面。", "fact_refs": ["synthetic"],
                "visuals": [{"source": "raw clips/导航 测试.mp4", "start": 0.0, "duration": 2.2}],
                "captions": [{"start": 0.0, "end": 1.8, "text": "打开测试页面。"}],
                "overlay": "none", "base_scale": 1.0, "transform_origin": "50% 50%", "masks": []
            },
            {
                "id": "scene-02", "title": "Result", "narration": "查看测试结果。", "fact_refs": ["synthetic"],
                "visuals": [{"source": "raw clips/结果 test.mp4", "start": 0.0, "duration": 2.2}],
                "captions": [{"start": 0.0, "end": 1.8, "text": "查看测试结果。"}],
                "overlay": "success", "base_scale": 1.0, "transform_origin": "50% 50%", "masks": []
            }
        ]
    }
    (output / "edit-spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "spec": str(output / "edit-spec.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
