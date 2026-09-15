#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from _common import emit, probe_media, resolve_ffmpeg, sha256_file


def rejected_name(output: Path, reason: str) -> Path:
    clean = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in reason).strip("-")
    return output.with_name(f"{output.stem}.rejected-{clean or 'unknown'}{output.suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Record one naturally completing macOS display segment with JSON handshakes.")
    parser.add_argument("--seconds", type=float, required=True)
    parser.add_argument("--display", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--show-clicks", action="store_true")
    parser.add_argument("--ready-delay", type=float, default=0.75)
    parser.add_argument("--timeout", type=float, default=None, help="Hard backend timeout; default is seconds + 30.")
    parser.add_argument("--min-duration-ratio", type=float, default=0.8)
    parser.add_argument("--screencapture", default="/usr/sbin/screencapture")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.seconds < 1 or args.seconds > 1800:
        parser.error("--seconds must be between 1 and 1800")
    if args.display < 1:
        parser.error("--display must be >= 1")
    timeout = args.timeout if args.timeout is not None else args.seconds + 30
    if timeout <= args.ready_delay:
        parser.error("--timeout must exceed --ready-delay")
    output = args.output.expanduser().resolve()
    if output.suffix.lower() not in {".mov", ".mp4"}:
        parser.error("--output must end in .mov or .mp4")
    if output.exists() and not args.overwrite:
        parser.error("output exists; use --overwrite or a new take name")
    if not os.access(args.screencapture, os.X_OK):
        parser.error("screencapture backend is not executable")

    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        args.screencapture,
        "-v",
        f"-V{args.seconds}",
        f"-D{args.display}",
        "-x",
    ]
    if args.show_clicks:
        command.append("-k")
    command.append(str(output))

    if args.dry_run:
        emit("DRY_RUN", command=command, privacy_scope=f"entire display {args.display}")
        return 0

    start = time.monotonic()
    process = subprocess.Popen(command)
    try:
        time.sleep(args.ready_delay)
        if process.poll() is not None:
            retained = None
            if output.exists():
                rejected = rejected_name(output, "before-ready")
                output.rename(rejected)
                retained = str(rejected)
            emit("REJECTED", reason="backend-exited-before-ready", returncode=process.returncode, retained_as=retained)
            return 2
        emit(
            "READY",
            backend="macos-screencapture-display" if Path(args.screencapture).resolve() == Path("/usr/sbin/screencapture") else "injected-recorder-backend",
            display=args.display,
            seconds=args.seconds,
            privacy_scope=f"entire display {args.display}",
            ready_evidence="direct non-interactive recorder alive after start delay",
        )
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        retained = None
        if output.exists():
            rejected = rejected_name(output, "timeout")
            output.rename(rejected)
            retained = str(rejected)
        emit("REJECTED", reason="timeout", timeout=timeout, retained_as=retained)
        return 6
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        if output.exists():
            output.rename(rejected_name(output, "interrupted"))
        emit("REJECTED", reason="interrupted", observed_behavior="artifact not accepted")
        return 130

    elapsed = time.monotonic() - start
    if returncode != 0:
        if output.exists():
            output.rename(rejected_name(output, f"exit-{returncode}"))
        emit("REJECTED", reason="backend-failure", returncode=returncode, elapsed=round(elapsed, 3))
        return 3

    try:
        ff = resolve_ffmpeg()
        probe = probe_media(output, ff["ffprobe"])
        duration = float(probe["format"]["duration"])
        has_video = any(stream.get("codec_type") == "video" for stream in probe.get("streams", []))
    except Exception as exc:
        if output.exists():
            output.rename(rejected_name(output, "unprobeable"))
        emit("REJECTED", reason="unprobeable", detail=str(exc))
        return 4

    if elapsed < args.seconds * 0.8 or duration < args.seconds * args.min_duration_ratio or not has_video:
        rejected = rejected_name(output, "too-short")
        output.rename(rejected)
        emit(
            "REJECTED",
            reason="too-short",
            elapsed=round(elapsed, 3),
            media_duration=round(duration, 3),
            retained_as=str(rejected),
        )
        return 5

    emit(
        "COMPLETED",
        output=str(output),
        elapsed=round(elapsed, 3),
        media_duration=round(duration, 3),
        sha256=sha256_file(output),
        probe=probe,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
