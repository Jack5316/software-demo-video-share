#!/usr/bin/env python3
"""Batch TTS generation CLI.

用法：
    python3 tts_cli.py <scripts.json> <out_dir>

scripts.json 格式（数组）：
    [
      {
        "slug": "backprop",
        "script": "神经网络的学习本质就是反向传播...",
        "pronunciation_dict": ["自定义/替换"]   // 可选，追加到全局字典
      },
      ...
    ]

输出：
    <out_dir>/<slug>.mp3
    <out_dir>/<slug>.duration   （秒数，字符串，供 timeline 对齐）

幂等：<slug>.mp3 已存在且非空则跳过（省 API 额度）。
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pronunciation import apply_text_replacements
from tts import synthesize, begin_batch, last_metadata


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ]).decode().strip()
    return float(out)


def main():
    if len(sys.argv) != 3:
        print("用法: python3 tts_cli.py <scripts.json> <out_dir>", file=sys.stderr)
        sys.exit(2)

    scripts_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    scripts = json.loads(scripts_path.read_text())
    if not isinstance(scripts, list):
        print("错误: scripts.json 必须是 list", file=sys.stderr)
        sys.exit(1)

    begin_batch()
    for item in scripts:
        slug = item["slug"]
        text = apply_text_replacements(item["script"])
        extra_dict = item.get("pronunciation_dict")

        mp3 = out_dir / f"{slug}.mp3"
        print(f"[{slug}] resolving cached/generated audio...", flush=True)
        audio = synthesize(text, pronunciation_dict=extra_dict, provider=item.get("provider"), speed=item.get("speed", 1.0))
        mp3.with_suffix(".route.json").write_text(json.dumps(last_metadata(), ensure_ascii=False, indent=2))
        mp3.write_bytes(audio)

        dur = ffprobe_duration(mp3)
        (out_dir / f"{slug}.duration").write_text(f"{dur:.3f}")
        print(f"  -> {mp3.name}  {dur:.2f}s")


if __name__ == "__main__":
    main()
