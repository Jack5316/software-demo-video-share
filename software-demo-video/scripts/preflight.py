#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from _common import probe_media, resolve_ffmpeg, sha256_file


def configured_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    names: set[str] = set()
    pattern = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = pattern.match(line)
        if match:
            names.add(match.group(1))
    return names


def command_version(command: str) -> str | None:
    path = shutil.which(command)
    if not path:
        return None
    proc = subprocess.run([path, "--version"], capture_output=True, text=True)
    line = (proc.stdout or proc.stderr).splitlines()
    return line[0][:160] if line else path


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect local software-demo video capability without exposing secrets.")
    parser.add_argument("--capture-mode", choices=["window", "display"], default="window")
    parser.add_argument("--json", action="store_true", help="Emit JSON (default is a compact text summary).")
    parser.add_argument("--secrets", default="~/.config/voice-clone/secrets.env", help="Secrets carrier to inspect by key name only.")
    parser.add_argument("--recording-evidence", type=Path, help="Previously completed low-risk recorder probe.")
    parser.add_argument("--render-evidence", type=Path, help="Previously completed low-risk rendered-video probe.")
    args = parser.parse_args()

    secrets_path = Path(args.secrets).expanduser()
    configured = configured_names(secrets_path) | set(os.environ)
    recorder = "/usr/sbin/screencapture"
    help_proc = subprocess.run([recorder, "-h"], capture_output=True, text=True) if Path(recorder).exists() else None
    help_text = (help_proc.stdout + help_proc.stderr) if help_proc else ""
    flags = {flag: flag in help_text for flag in ["-v", "-V", "-D", "-k"]}
    overlay = subprocess.run(["pgrep", "-x", "screencaptureui"], capture_output=True).returncode == 0

    try:
        ff = resolve_ffmpeg()
        ff_error = None
    except Exception as exc:
        ff = None
        ff_error = str(exc)

    remotion_root = Path(os.environ.get("SOFTWARE_DEMO_NODE_MODULES", str(Path(__file__).resolve().parents[1] / "assets/remotion-template/node_modules"))) / "remotion"
    mac_version = platform.mac_ver()[0]
    window_capable = bool(mac_version and int(mac_version.split(".")[0]) >= 15 and shutil.which("xcrun"))
    result = {
        "recorder": {
            "path": recorder if Path(recorder).exists() else None,
            "display_video_flags": flags,
            "window_backend_prerequisites": window_capable,
            "window_backend": "scripts/WindowRecorder.swift",
            "selected_mode": args.capture_mode,
            "window_capture_requires_compilation_and_pixel_probe": True,
            "recorder_overlay_process_present": overlay,
            "visual_cleanliness_requires_screenshot_review": True,
        },
        "ffmpeg": ff,
        "ffmpeg_error": ff_error,
        "node": command_version("node"),
        "npm": command_version("npm"),
        "remotion_runtime_on_disk": remotion_root.exists(),
        "configuration": {
            "MINIMAX_TTS_API_KEY": "MINIMAX_TTS_API_KEY" in configured,
            "MINIMAX_VOICE_ID": "MINIMAX_VOICE_ID" in configured,
        },
    }
    recording_verified = False
    rendering_verified = False
    recording_evidence = None
    render_evidence = None
    if ff and args.recording_evidence:
        try:
            recording_path = args.recording_evidence.expanduser().resolve()
            recording_verified = any(stream.get("codec_type") == "video" for stream in probe_media(recording_path, ff["ffprobe"]).get("streams", []))
            if recording_verified:
                recording_evidence = {"path": str(recording_path), "sha256": sha256_file(recording_path)}
        except Exception:
            recording_verified = False
    if ff and args.render_evidence:
        try:
            render_path = args.render_evidence.expanduser().resolve()
            render_probe = probe_media(render_path, ff["ffprobe"])
            rendering_verified = {stream.get("codec_type") for stream in render_probe.get("streams", [])} >= {"video", "audio"}
            if rendering_verified:
                render_evidence = {"path": str(render_path), "sha256": sha256_file(render_path)}
        except Exception:
            rendering_verified = False
    result["probe_evidence"] = {"recording": recording_evidence, "render": render_evidence}
    local_ready = False
    service = Path(__file__).resolve().parents[2] / 'minimax-tts/scripts'
    result['narration_route'] = {'bundled_scripts': (service/'tts.py').is_file(), 'runtime_not_probed': True}
    result["ready"] = {
        "display_capture": bool(result["recorder"]["path"] and all(flags.values())),
        "cloned_narration_configured": local_ready or all(result["configuration"][key] for key in ["MINIMAX_TTS_API_KEY", "MINIMAX_VOICE_ID"]),
        "scene_rendering": bool(ff and result["node"] and result["remotion_runtime_on_disk"]),
        "recording_media_probe_verified": recording_verified,
        "render_media_probe_verified": rendering_verified,
        "window_capture_prerequisites": window_capable,
        "end_to_end_verified": False,
        "end_to_end_note": "Media structure alone cannot verify UI actions, capture scope, cloned voice or semantic sync; require final review and run report.",
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for key, value in result["ready"].items():
            print(f"{key}={str(value).lower()}")
    return 0 if ff and (window_capable if args.capture_mode == "window" else result["ready"]["display_capture"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
