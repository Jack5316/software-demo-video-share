#!/usr/bin/env python3
"""TTS with cue-level timing.

生成音频时把脚本按 cue（标注的关键时间点）切片，每个 cue 独立 TTS。
每段时长用 ffprobe 精确测量 → 累加得到每个 cue 的绝对起止时间 →
写入 <slug>.cues.json。最终 mp3 由 ffmpeg concat 拼接（可选静音换气）。

下游（interactive-html / manim / remotion 等）的 buildTimeline 直接引用
CUES.<id>.start，动画节拍和旁白毫秒级对齐，不再靠手工估算。

Input spec:
    {
      "slug": "ih-dnn-architecture",
      "voice_id": "optional, defaults to $MINIMAX_VOICE_ID",
      "speed": 1.0,
      "silence_gap_ms": 150,   // 相邻 cue 之间的静音换气（默认 150ms）
      "pronunciation_dict": [...],  // optional, caller 自定义追加字典
      "cues": [
        {"id": "intro",  "text": "DNN 到底怎么算？"},
        {"id": "focus1", "text": "进第一个隐藏层..."},
        ...
      ]
    }

Output (written to out_dir):
    <slug>.mp3        — 拼接后的最终音频
    <slug>.cues.json — 精确时间清单
      {
        "slug": "...",
        "duration": 50.18,
        "gap_s": 0.15,
        "cues": [
          {"id": "intro",  "start": 0.000, "end": 1.402, "text": "..."},
          {"id": "focus1", "start": 1.552, "end": 8.930, "text": "..."},
          ...
        ]
      }

Usage:
    python3 tts_cued.py <spec.json> <out_dir>
"""
from __future__ import annotations
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tts import synthesize, begin_batch, last_metadata  # noqa: E402
from pronunciation import apply_text_replacements  # noqa: E402


def ffprobe_duration(path: Path) -> float:
    """精确测量 mp3 时长（秒）。"""
    out = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ])
    return float(out.decode().strip())


def generate_silence(duration_s: float, sample_rate: int, bitrate: int, out_path: Path) -> None:
    """生成固定时长的静音 mp3，用于 cue 之间的换气。"""
    subprocess.check_call([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r={sample_rate}:cl=mono",
        "-t", f"{duration_s}",
        "-b:a", f"{bitrate}",
        str(out_path),
    ])


def concat_audio(files: list, out_path: Path) -> None:
    """用 ffmpeg concat demuxer 拼接 mp3。

    BUG FIX 2026-04-19: list 文件写入 /tmp/，而 `file '...'` 里给 ffmpeg 的路径若是
    相对路径，ffmpeg 会基于 list 文件所在目录（/tmp/）解析 → 找不到文件 (exit 254)。
    必须用 `Path(fp).resolve()` 转绝对路径。
    """
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        list_path = f.name
        for fp in files:
            abs_fp = Path(fp).resolve()
            # concat demuxer 要求 single-quote 包围；路径必须绝对
            f.write(f"file '{abs_fp}'\n")
    try:
        subprocess.check_call([
            "ffmpeg", "-v", "error", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c", "copy",
            str(out_path),
        ])
    finally:
        Path(list_path).unlink(missing_ok=True)


def generate_cued(
    spec_path: str,
    out_dir: str,
    inter_cue_delay: float | None = None,
    rpm_limit: int = 10,
) -> dict:
    """主入口：读 spec → 逐 cue TTS → 拼接 → 写清单。

    Args:
        spec_path: 输入 spec JSON 路径
        out_dir: 输出目录（会创建）
        inter_cue_delay: 两次 API 调用之间 `time.sleep()` 的秒数（**不含** API response time）。
            None (默认) → 按 `rpm_limit` 算保守值：`60/rpm_limit + 1`。
            显式传数值则覆盖自动计算（用于压榨或调试）。
        rpm_limit: 账户 RPM 配额。MiniMax T2A v2 标准账户 = 10（2026-04-19 实证）。
            升级 tier（如企业 60 RPM）时传 60。
            公式：sleep = 60/rpm + 1，start-to-start = sleep + response(~1-3s) ≥ 60/rpm，稳不碰线。
    """
    if inter_cue_delay is None:
        inter_cue_delay = 60.0 / rpm_limit + 1.0
    begin_batch()
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    slug = spec["slug"]
    cues = spec["cues"]
    voice_id = spec.get("voice_id")
    speed = spec.get("speed", 1.0)
    gap_ms = spec.get("silence_gap_ms", 150)
    gap_s = gap_ms / 1000.0
    sample_rate = spec.get("sample_rate", 32000)
    bitrate = spec.get("bitrate", 128000)
    pronunciation_dict = spec.get("pronunciation_dict")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    work = out / f".cued-{slug}"
    work.mkdir(exist_ok=True)

    # 1. silence pad（只生成一次）
    silence_path = work / "silence.mp3"
    if gap_s > 0:
        generate_silence(gap_s, sample_rate, bitrate, silence_path)

    # 2. 逐 cue TTS + ffprobe
    frag_files = []
    frag_durs = []
    for i, cue in enumerate(cues):
        cue_id = cue["id"]
        raw_text = cue["text"]
        text = apply_text_replacements(raw_text)
        fp = work / f"{i:02d}-{cue_id}.mp3"
        print(f"[{slug}] [{i+1:02d}/{len(cues):02d}] {cue_id}: {len(text)} chars", flush=True)

        audio_bytes = synthesize(
            text=text,
            voice_id=voice_id,
            speed=cue.get("speed", speed),
            provider=spec.get("provider"),
            pronunciation_dict=pronunciation_dict,
            sample_rate=sample_rate,
            bitrate=bitrate,
        )
        route = last_metadata()
        fp.with_suffix(".route.json").write_text(json.dumps(route, ensure_ascii=False, indent=2))
        cue["generation"] = route
        fp.write_bytes(audio_bytes)
        dur = ffprobe_duration(fp)
        frag_durs.append(dur)
        frag_files.append(fp)
        print(f"  → {dur:.3f}s", flush=True)

        # 防 TPM 限流
        if i < len(cues) - 1 and inter_cue_delay > 0 and route.get("provider") == "minimax" and not route.get("request_cache_hit"):
            time.sleep(inter_cue_delay)

    # 3. 拼接 concat list（cue 之间插静音）
    concat_list = []
    for i, fp in enumerate(frag_files):
        concat_list.append(fp)
        if gap_s > 0 and i < len(frag_files) - 1:
            concat_list.append(silence_path)

    # 4. ffmpeg concat → final mp3
    final_mp3 = out / f"{slug}.mp3"
    concat_audio(concat_list, final_mp3)
    final_dur = ffprobe_duration(final_mp3)

    # 5. 计算每个 cue 的 start/end（累加法）
    timings = []
    t = 0.0
    for i, (cue, dur) in enumerate(zip(cues, frag_durs)):
        timings.append({
            "id": cue["id"],
            "start": round(t, 3),
            "end": round(t + dur, 3),
            "text": cue["text"],
            "generation": cue.get("generation"),
        })
        t += dur
        if gap_s > 0 and i < len(cues) - 1:
            t += gap_s

    # 用 ffprobe 的最终 duration 对账（理论 t 应等于 final_dur，误差 < 0.02s）
    manifest = {
        "slug": slug,
        "duration": round(final_dur, 3),
        "duration_computed": round(t, 3),
        "gap_s": gap_s,
        "voice_id": voice_id,
        "n_cues": len(cues),
        "cues": timings,
    }
    out_json = out / f"{slug}.cues.json"
    out_json.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # 6. cleanup work dir（保留片段以便 debug 可以去掉这行）
    shutil.rmtree(work)

    drift = abs(final_dur - t)
    drift_note = f" (drift {drift*1000:.0f}ms from computed)" if drift > 0.005 else ""
    print(f"✓ {final_mp3.name}  {final_dur:.2f}s{drift_note}")
    print(f"✓ {out_json.name}  {len(cues)} cues")
    return manifest


def main():
    if len(sys.argv) < 3:
        print(
            "Usage: tts_cued.py <spec.json> <out_dir> [--rpm N] [--inter-cue-delay SECONDS]\n"
            "  --rpm N              账户 RPM 配额（MiniMax T2A v2 标准=10，企业=60）。默认 10。\n"
            "                       自动算 sleep = 60/rpm + 1（保守 1s 缓冲）\n"
            "  --inter-cue-delay S  显式指定 sleep 秒数（覆盖 --rpm 自动计算）。\n"
            "                       注：这是 time.sleep() 的数值，不含 API response time。",
            file=sys.stderr,
        )
        sys.exit(2)
    spec_path = sys.argv[1]
    out_dir = sys.argv[2]
    rpm = 10  # MiniMax T2A v2 标准账户默认
    if "--rpm" in sys.argv:
        rpm = int(sys.argv[sys.argv.index("--rpm") + 1])
    delay: float | None = None
    if "--inter-cue-delay" in sys.argv:
        delay = float(sys.argv[sys.argv.index("--inter-cue-delay") + 1])
    generate_cued(spec_path, out_dir, inter_cue_delay=delay, rpm_limit=rpm)


if __name__ == "__main__":
    main()
