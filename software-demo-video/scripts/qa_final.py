#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from pathlib import Path

from _common import probe_media, resolve_ffmpeg, sha256_file


SRT_TIME = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")


def seconds(value: str) -> float:
    match = SRT_TIME.fullmatch(value.strip())
    if not match:
        raise ValueError(f"bad SRT time: {value}")
    h, m, s, ms = map(int, match.groups())
    return h * 3600 + m * 60 + s + ms / 1000


def parse_srt(path: Path) -> list[dict]:
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip())
    result = []
    last_end = 0.0
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 3 or " --> " not in lines[1]:
            raise ValueError("malformed SRT block")
        start_text, end_text = lines[1].split(" --> ", 1)
        start, end = seconds(start_text), seconds(end_text)
        if start < last_end or end <= start:
            raise ValueError("overlapping or reversed SRT timing")
        result.append({"start": start, "end": end, "text": "\n".join(lines[2:])})
        last_end = end
    if not result:
        raise ValueError("SRT has no captions")
    return result


def validate_scene_plan(plan: dict) -> float:
    required = {"version", "fps", "width", "height", "audioSampleRate", "outputFilename", "scenes"}
    if set(plan) != required or plan["version"] != "software-demo-video.scene-plan/v1":
        raise ValueError("invalid scene-plan structure/version")
    if not isinstance(plan["scenes"], list) or not plan["scenes"] or plan["fps"] <= 0:
        raise ValueError("scene-plan scenes/fps invalid")
    ids = [scene.get("id") for scene in plan["scenes"]]
    if len(ids) != len(set(ids)) or any(not value for value in ids):
        raise ValueError("scene-plan ids invalid")
    total_frames = 0
    for scene in plan["scenes"]:
        if not isinstance(scene.get("durationInFrames"), int) or scene["durationInFrames"] <= 0:
            raise ValueError("scene duration invalid")
        total_frames += scene["durationInFrames"]
    return total_frames / float(plan["fps"])


def extract_full_frames(video: Path, plan: dict, out_dir: Path, interval: float, ffmpeg: str) -> list[dict]:
    frames_dir = out_dir / "interval-frames"
    scene_dir = out_dir / "scene-frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    scene_dir.mkdir(parents=True, exist_ok=True)
    for old in list(frames_dir.glob("*.png")) + list(scene_dir.glob("*.png")):
        old.unlink()
    subprocess.run([
        ffmpeg, "-y", "-v", "error", "-i", str(video),
        "-vf", f"fps=1/{interval},scale=960:-1", str(frames_dir / "frame-%04d.png"),
    ], check=True)
    interval_files = sorted(frames_dir.glob("*.png"))
    fps = float(plan["fps"])
    cursor = 0.0
    scene_files: list[Path] = []
    for scene in plan["scenes"]:
        duration = float(scene["durationInFrames"]) / fps
        points = {
            "first": cursor + min(0.15, duration / 4),
            "middle": cursor + duration / 2,
            "last": cursor + max(duration - 0.15, duration / 2),
        }
        for label, point in points.items():
            target = scene_dir / f"{scene['id']}-{label}.png"
            subprocess.run([
                ffmpeg, "-y", "-v", "error", "-ss", f"{point:.3f}",
                "-i", str(video), "-frames:v", "1", "-vf", "scale=1280:-1", str(target),
            ], check=True)
            scene_files.append(target)
        cursor += duration
    if len(scene_files) != len(plan["scenes"]) * 3:
        raise ValueError("scene-frame coverage incomplete")
    all_files = interval_files + scene_files
    return [
        {"path": str(path.relative_to(out_dir)), "sha256": sha256_file(path)}
        for path in all_files
    ]


def risk_points(duration: float, extra: dict | None = None) -> list[dict]:
    """Small baseline, then caller-selected locations justified by actual risk."""
    points = [
        {"time": min(0.5, duration / 4), "reason": "opening state and framing"},
        {"time": duration / 2, "reason": "baseline layout and subtitle sample"},
        {"time": max(0, duration - 0.5), "reason": "ending and late timing sample"},
    ]
    if extra is not None:
        if not isinstance(extra, dict) or set(extra) != {"points"} or not isinstance(extra["points"], list):
            raise ValueError("samples must be an object containing a points list")
        points += extra["points"]
    selected = {}
    for point in points:
        if not isinstance(point, dict) or set(point) != {"time", "reason"}:
            raise ValueError("each sample requires time and reason")
        t, reason = point["time"], point["reason"]
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or not 0 <= t < duration:
            raise ValueError("sample time must be finite and inside final video")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("sample reason must be nonempty")
        # Merge duplicate frame requests without discarding their risk rationale.
        key = round(t, 6)
        if key in selected:
            selected[key]["reason"] += "; " + reason.strip()
        else:
            selected[key] = {"time": float(t), "reason": reason.strip()}
    return sorted(selected.values(), key=lambda item: item["time"])


def extract_samples(video: Path, points: list[dict], out_dir: Path, ffmpeg: str) -> list[dict]:
    folder = out_dir / "sample-frames"
    folder.mkdir(parents=True, exist_ok=True)
    evidence = []
    for i, point in enumerate(points):
        target = folder / f"sample-{i+1:04d}.png"
        target.unlink(missing_ok=True)  # Empty decode must not reuse an old frame.
        subprocess.run([ffmpeg, "-y", "-v", "error", "-ss", str(point["time"]),
                        "-i", str(video), "-frames:v", "1", "-vf", "scale=1280:-1", str(target)], check=True)
        evidence.append({"path": str(target.relative_to(out_dir)), "sha256": sha256_file(target)})
    return evidence


def reusable_frames(manifest: dict, hashes: dict, sampling: dict, engine: str, out_dir: Path) -> bool:
    if not (manifest.get("artifact_sha256") == hashes["artifact_sha256"]
            and manifest.get("scene_plan_sha256") == hashes["scene_plan_sha256"]
            and manifest.get("sampling") == sampling and manifest.get("qa_engine_sha256") == engine):
        return False
    evidence = manifest.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return False
    if sampling.get("mode") == "risk" and len(evidence) != len(sampling["points"]):
        return False
    try:
        if len({item["path"] for item in evidence}) != len(evidence):
            return False
        for item in evidence:
            target = (out_dir / item["path"]).resolve()
            if not target.is_relative_to(out_dir.resolve()) or not target.is_file() or sha256_file(target) != item["sha256"]:
                return False
    except (KeyError, TypeError, OSError):
        return False
    return True


def audio_metrics(video: Path, ffmpeg: str) -> dict:
    ebu = subprocess.run([
        ffmpeg, "-hide_banner", "-i", str(video), "-filter_complex", "ebur128=peak=true", "-f", "null", "-",
    ], capture_output=True, text=True)
    text = ebu.stdout + ebu.stderr
    summary = text.rsplit("Summary:", 1)[-1] if "Summary:" in text else ""
    integrated_match = re.search(r"Integrated loudness:.*?I:\s+(-?[\d.]+) LUFS", summary, re.S)
    lra_match = re.search(r"Loudness range:.*?LRA:\s+([\d.]+) LU", summary, re.S)
    peak_match = re.search(r"True peak:.*?Peak:\s+(-?[\d.]+) dBFS", summary, re.S)
    integrated = integrated_match.group(1) if integrated_match else None
    lra = lra_match.group(1) if lra_match else None
    peak = peak_match.group(1) if peak_match else None
    astats = subprocess.run([
        ffmpeg, "-hide_banner", "-i", str(video), "-af", "astats=metadata=1:reset=0", "-f", "null", "-",
    ], capture_output=True, text=True)
    atext = astats.stdout + astats.stderr
    nan_values = [float(value) for value in re.findall(r"Number of NaNs:\s+([\d.]+)", atext)]
    inf_values = [float(value) for value in re.findall(r"Number of Infs:\s+([\d.]+)", atext)]
    return {
        "integrated_lufs": float(integrated) if integrated is not None else None,
        "loudness_range_lu": float(lra) if lra is not None else None,
        "true_peak_dbfs": float(peak) if peak is not None else None,
        "nan_count": max(nan_values, default=0.0),
        "inf_count": max(inf_values, default=0.0),
    }


def metric_gate(metrics: dict) -> tuple[bool, str]:
    integrated = metrics["integrated_lufs"]
    peak = metrics["true_peak_dbfs"]
    if integrated is None or peak is None:
        return False, "loudness metrics missing (silent/invalid audio)"
    if not -18.5 <= integrated <= -13.5:
        return False, "integrated loudness outside -18.5..-13.5 LUFS"
    if peak > -0.8:
        return False, "true peak exceeds -0.8 dBFS"
    if metrics["nan_count"] or metrics["inf_count"]:
        return False, "NaN/Inf samples detected"
    return True, "audio metrics pass"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate multi-artifact SHA-bound evidence and enforce review verdict.")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--srt", type=Path, required=True)
    parser.add_argument("--scene-plan", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--samples", type=Path, help="Risk points JSON: {points: [{time, reason}]} in final-video seconds")
    parser.add_argument("--full-scan", action="store_true", help="Explicit exhaustive scene/interval sampling; not the default")
    parser.add_argument("--interval", type=float, default=None, help="Explicit interval scan; implies --full-scan")
    parser.add_argument("--verdict", type=Path)
    parser.add_argument("--require-verdict", action="store_true")
    args = parser.parse_args()
    if args.interval is not None and (not math.isfinite(args.interval) or args.interval <= 0):
        parser.error("--interval must be positive")

    if args.samples and (args.full_scan or args.interval is not None):
        parser.error("choose risk samples or explicit full scan, not both")

    video, srt, plan_path = (path.expanduser().resolve() for path in [args.video, args.srt, args.scene_plan])
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    tools = resolve_ffmpeg()
    probe = probe_media(video, tools["ffprobe"])
    duration = float(probe["format"]["duration"])
    streams = probe.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if not video_stream or not audio_stream:
        raise ValueError("final video/audio stream missing")
    captions = parse_srt(srt)
    if captions[-1]["end"] > duration + 0.5:
        raise ValueError("SRT exceeds video duration")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    planned_duration = validate_scene_plan(plan)
    timeline_ok = abs(planned_duration - duration) <= 0.5
    stream_ok = (
        int(video_stream.get("width", 0)) == int(plan["width"])
        and int(video_stream.get("height", 0)) == int(plan["height"])
        and int(audio_stream.get("sample_rate", 0)) == int(plan["audioSampleRate"])
    )
    hashes = {
        "artifact_sha256": sha256_file(video),
        "srt_sha256": sha256_file(srt),
        "scene_plan_sha256": sha256_file(plan_path),
    }
    engine = sha256_file(Path(__file__)) + ":" + sha256_file(Path(__file__).with_name("_common.py"))
    full_scan = args.full_scan or args.interval is not None
    sampling = ({"mode": "full", "interval_seconds": args.interval or 3.0}
                if full_scan else {"mode": "risk", "points": risk_points(duration,
                    json.loads(args.samples.read_text()) if args.samples else None)})
    old_manifest_path, old_report_path = out_dir / "evidence-manifest.json", out_dir / "machine-qa.json"
    def previous(path):
        try:
            data = json.loads(path.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}
    old_manifest, old_report = previous(old_manifest_path), previous(old_report_path)
    frames_reused = reusable_frames(old_manifest, hashes, sampling, engine, out_dir)
    if frames_reused:
        evidence = old_manifest["evidence"]
    elif full_scan:
        evidence = extract_full_frames(video, plan, out_dir, sampling["interval_seconds"], tools["ffmpeg"])
    else:
        evidence = extract_samples(video, sampling["points"], out_dir, tools["ffmpeg"])
    audio_reused = (old_report.get("artifact_sha256") == hashes["artifact_sha256"]
                    and old_report.get("qa_engine_sha256") == engine
                    and isinstance(old_report.get("audio"), dict)
                    and set(old_report["audio"]) == {"integrated_lufs", "loudness_range_lu", "true_peak_dbfs", "nan_count", "inf_count"})
    metrics = old_report["audio"] if audio_reused else audio_metrics(video, tools["ffmpeg"])
    audio_ok, audio_reason = metric_gate(metrics)
    evidence_manifest = {**hashes, "sampling": sampling, "qa_engine_sha256": engine, "evidence": evidence}
    evidence_path = out_dir / "evidence-manifest.json"
    evidence_path.write_text(json.dumps(evidence_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence_sha = sha256_file(evidence_path)

    required_pass = ["status", "privacy", "source_accuracy", "semantic_fidelity", "subtitles", "visual_quality"]
    verdict_status, verdict_reason = "MISSING", "no verdict supplied"
    if args.verdict:
        verdict = json.loads(args.verdict.read_text(encoding="utf-8"))
        expected_hashes = {**hashes, "evidence_manifest_sha256": evidence_sha}
        if any(verdict.get(key) != value for key, value in expected_hashes.items()):
            verdict_status, verdict_reason = "STALE", "MP4/SRT/scene-plan/evidence hash mismatch"
        elif any(verdict.get(field) != "PASS" for field in required_pass):
            verdict_status, verdict_reason = "FAIL", "one or more review fields are not PASS"
        elif verdict.get("reviewed_evidence") != evidence:
            verdict_status, verdict_reason = "FAIL", "reviewed evidence coverage/hash list mismatch"
        elif not re.fullmatch(r"\d{4}-\d{2}-\d{2}T.+", str(verdict.get("reviewed_at", ""))) or not verdict.get("reviewer"):
            verdict_status, verdict_reason = "FAIL", "review metadata incomplete"
        else:
            verdict_status, verdict_reason = "PASS", "artifact hashes and selected risk samples reviewed"

    delivery_ready = verdict_status == "PASS" and audio_ok and timeline_ok and stream_ok
    report = {
        "artifact": str(video), **hashes,
        "qa_engine_sha256": engine, "sampling": sampling,
        "frames_reused": frames_reused, "audio_metrics_reused": audio_reused,
        "evidence_manifest_sha256": evidence_sha,
        "probe": probe,
        "duration": duration,
        "planned_duration": planned_duration,
        "timeline_ok": timeline_ok,
        "stream_contract_ok": stream_ok,
        "captions": {"count": len(captions), "last_end": captions[-1]["end"]},
        "audio": metrics,
        "audio_contract_ok": audio_ok,
        "audio_reason": audio_reason,
        "evidence": evidence,
        "verdict_status": verdict_status,
        "verdict_reason": verdict_reason,
        "delivery_ready": delivery_ready,
    }
    report_path = out_dir / "machine-qa.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report_path), **hashes, "evidence_manifest_sha256": evidence_sha, "delivery_ready": delivery_ready}, ensure_ascii=False))
    if args.require_verdict and not delivery_ready:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
