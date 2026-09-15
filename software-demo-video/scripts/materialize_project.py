#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from _common import load_edit_spec, probe_media, resolve_ffmpeg, resolve_source, sha256_file


def encoder_args(encoder: str) -> list[str]:
    if encoder == "libx264":
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
    return ["-c:v", "h264_videotoolbox", "-b:v", "8M", "-pix_fmt", "yuv420p"]


def cue_map(cues_path: Path) -> tuple[list[dict], dict[str, dict]]:
    payload = json.loads(cues_path.read_text(encoding="utf-8"))
    cues = payload.get("cues")
    if not isinstance(cues, list) or not cues:
        raise ValueError("cues JSON has no cues")
    previous_end = 0.0
    for cue in cues:
        if not {"id", "start", "end", "text"} <= set(cue):
            raise ValueError("cue fields incomplete")
        start, end = float(cue["start"]), float(cue["end"])
        if not math.isfinite(start) or not math.isfinite(end) or start < previous_end or end <= start or not isinstance(cue["text"], str):
            raise ValueError("cue ordering/timing/text invalid")
        previous_end = end
    result = {cue["id"]: cue for cue in cues}
    if len(result) != len(cues):
        raise ValueError("duplicate cue ids")
    return cues, result


def render_visual(
    ffmpeg: str,
    encoder: str,
    visuals: list[dict],
    spec_path: Path,
    target_seconds: float,
    width: int,
    height: int,
    fps: int,
    output: Path,
) -> list[dict]:
    retained_seconds = sum(v["duration"] / v.get("playback_rate", 1) for v in visuals)
    if retained_seconds > target_seconds + 1 / fps:
        raise ValueError("visual actions exceed narration slot; select tighter source ranges or explicit playback_rate; refusing silent truncation")
    command = [ffmpeg, "-y", "-v", "error"]
    resolved: list[dict] = []
    for visual in visuals:
        source = resolve_source(spec_path, visual["source"])
        if not source.exists():
            raise FileNotFoundError(f"visual source missing: {source}")
        video_streams = [s for s in probe_media(source)["streams"] if s.get("codec_type") == "video"]
        if not video_streams or "duration" not in video_streams[0]:
            raise ValueError("visual source requires a video stream with measurable duration")
        media_duration = float(video_streams[0]["duration"])
        if visual["start"] + visual["duration"] > media_duration + 1 / fps:
            raise ValueError("visual source range exceeds actual media duration")
        command += ["-ss", str(visual["start"]), "-t", str(visual["duration"]), "-i", str(source)]
        resolved.append({
            "source": str(source),
            "start": visual["start"],
            "duration": visual["duration"],
            "sha256": sha256_file(source),
            "playback_rate": visual.get("playback_rate", 1),
            "effective_duration": visual["duration"] / visual.get("playback_rate", 1),
        })

    chains = []
    labels = []
    for index in range(len(visuals)):
        label = f"v{index}"
        labels.append(f"[{label}]")
        chains.append(
            f"[{index}:v]setpts=(PTS-STARTPTS)/{visuals[index].get('playback_rate', 1)},fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,setpts=PTS-STARTPTS[{label}]"
        )
    chains.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[joined]")
    chains.append(
        # concat does not preserve a usable frame-rate hint for tpad on all
        # FFmpeg builds; restore it so short actions actually hold to the cue.
        f"[joined]fps={fps},tpad=stop_mode=clone:stop_duration={target_seconds:.6f},"
        f"trim=duration={target_seconds:.6f},setpts=PTS-STARTPTS[outv]"
    )
    command += ["-filter_complex", ";".join(chains), "-map", "[outv]", "-an"]
    command += encoder_args(encoder) + [str(output)]
    subprocess.run(command, check=True)
    return resolved


def split_audio(
    ffmpeg: str,
    combined: Path,
    start: float,
    duration: float,
    sample_rate: int,
    output: Path,
) -> float:
    subprocess.run([
        ffmpeg, "-y", "-v", "error",
        "-ss", f"{start:.6f}", "-t", f"{duration:.6f}", "-i", str(combined),
        "-c:a", "libmp3lame", "-b:a", "128k", "-ar", str(sample_rate), str(output),
    ], check=True)
    probe = probe_media(output)
    return float(probe["format"]["duration"])


def srt_time(value: float) -> str:
    milliseconds = max(0, round(value * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Instantiate and populate the reusable Remotion software-demo project.")
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--cues", type=Path, required=True)
    parser.add_argument("--combined-audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=None)
    parser.add_argument("--pad-frames", type=int, default=4)
    args = parser.parse_args()

    spec_path = args.spec.expanduser().resolve()
    spec = load_edit_spec(spec_path)
    cues_path = args.cues.expanduser().resolve()
    combined = args.combined_audio.expanduser().resolve()
    if not combined.exists():
        raise FileNotFoundError(combined)
    cue_list, cues = cue_map(cues_path)
    scene_ids = [scene["id"] for scene in spec["scenes"]]
    cue_ids = [cue["id"] for cue in cue_list]
    if scene_ids != cue_ids:
        raise ValueError("scene ids and cue ids must match exactly in order")
    combined_probe = probe_media(combined)
    combined_duration = float(combined_probe["format"]["duration"])
    if float(cue_list[-1]["end"]) > combined_duration + 0.1:
        raise ValueError("cues exceed combined-audio duration")

    skill_root = Path(__file__).resolve().parent.parent
    template = (args.template or (skill_root / "assets" / "remotion-template")).resolve()
    output = args.output.expanduser().resolve()
    if output == Path.home() or output == Path("/"):
        raise ValueError("refusing broad output directory")
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template, output, dirs_exist_ok=True, ignore=shutil.ignore_patterns("node_modules", "out"))
    (output / "public" / "audio").mkdir(parents=True, exist_ok=True)
    (output / "public" / "video").mkdir(parents=True, exist_ok=True)
    (output / "src").mkdir(parents=True, exist_ok=True)

    tools = resolve_ffmpeg()
    out_cfg = spec["output"]
    scene_plan = {
        "version": "software-demo-video.scene-plan/v1",
        "fps": out_cfg["fps"],
        "width": out_cfg["width"],
        "height": out_cfg["height"],
        "audioSampleRate": out_cfg["audio_sample_rate"],
        "outputFilename": out_cfg["filename"],
        "scenes": [],
    }
    evidence = {
        "ffmpeg": tools,
        "spec_sha256": sha256_file(spec_path),
        "cues_sha256": sha256_file(cues_path),
        "combined_audio_sha256": sha256_file(combined),
        "scenes": [],
    }

    for scene in spec["scenes"]:
        cue = cues[scene["id"]]
        if cue["text"] != scene["narration"]:
            raise ValueError(f"cue text does not match narration: {scene['id']}")
        cue_duration = float(cue["end"]) - float(cue["start"])
        audio_file = output / "public" / "audio" / f"{scene['id']}.mp3"
        actual_audio = split_audio(
            tools["ffmpeg"], combined, float(cue["start"]), cue_duration,
            out_cfg["audio_sample_rate"], audio_file,
        )
        frames = math.ceil(actual_audio * out_cfg["fps"]) + args.pad_frames
        target_seconds = frames / out_cfg["fps"]
        for caption in scene["captions"]:
            if caption["end"] > target_seconds + 0.05:
                raise ValueError(f"caption exceeds scene duration: {scene['id']}")
        for marker in scene.get("camera", []) + scene.get("clicks", []):
            if marker["t"] >= target_seconds:
                raise ValueError(f"motion cue exceeds scene duration: {scene['id']}")
        for mask in scene["masks"]:
            if mask["x"] + mask["width"] > out_cfg["width"] or mask["y"] + mask["height"] > out_cfg["height"]:
                raise ValueError(f"mask exceeds output bounds: {scene['id']}")

        video_file = output / "public" / "video" / f"{scene['id']}.mp4"
        sources = render_visual(
            tools["ffmpeg"], tools["encoder"], scene["visuals"], spec_path,
            target_seconds, out_cfg["width"], out_cfg["height"], out_cfg["fps"], video_file,
        )
        scene_plan["scenes"].append({
            "id": scene["id"],
            "title": scene["title"],
            "audioFile": audio_file.name,
            "videoFile": video_file.name,
            "durationInFrames": frames,
            "captions": scene["captions"],
            "overlay": scene["overlay"],
            "baseScale": scene["base_scale"],
            "transformOrigin": scene["transform_origin"],
            "masks": scene["masks"],
            **{key: scene[key] for key in ("camera", "clicks") if key in scene},
        })
        evidence["scenes"].append({
            "id": scene["id"],
            "audio_duration": actual_audio,
            "duration_in_frames": frames,
            "audio_sha256": sha256_file(audio_file),
            "video_sha256": sha256_file(video_file),
            "narration_sha256": hashlib.sha256(scene["narration"].encode("utf-8")).hexdigest(),
            "sources": sources,
            "hold_last_seconds": max(0, target_seconds - sum(v["effective_duration"] for v in sources)),
            "timing_quantization_tolerance_seconds": 1 / out_cfg["fps"],
        })

    plan_path = output / "src" / "scenePlan.json"
    plan_path.write_text(json.dumps(scene_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    srt_lines: list[str] = []
    caption_index = 1
    cursor = 0.0
    for source_scene, rendered_scene in zip(spec["scenes"], scene_plan["scenes"]):
        for caption in source_scene["captions"]:
            srt_lines.extend([
                str(caption_index),
                f"{srt_time(cursor + float(caption['start']))} --> {srt_time(cursor + float(caption['end']))}",
                caption["text"],
                "",
            ])
            caption_index += 1
        cursor += float(rendered_scene["durationInFrames"]) / float(scene_plan["fps"])
    (output / "out").mkdir(parents=True, exist_ok=True)
    srt_path = output / "out" / "final.srt"
    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    evidence["scene_plan_sha256"] = sha256_file(plan_path)
    evidence["srt_sha256"] = sha256_file(srt_path)
    evidence_path = output / "materialization.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"project": str(output), "scenes": len(scene_plan["scenes"]), "evidence": str(evidence_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
