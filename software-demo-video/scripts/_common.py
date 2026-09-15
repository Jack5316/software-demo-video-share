#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


class ContractError(ValueError):
    pass


def emit(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False), flush=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_json(command: list[str]) -> dict[str, Any]:
    proc = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(proc.stdout)


def select_encoders(encoders: str) -> dict[str, str]:
    video = "libx264" if "libx264" in encoders else (
        "h264_videotoolbox" if "h264_videotoolbox" in encoders else ""
    )
    if not video:
        raise RuntimeError("no supported H.264 encoder")
    if "libmp3lame" not in encoders:
        raise RuntimeError("libmp3lame missing")
    return {"encoder": video, "audio_encoder": "libmp3lame"}


def resolve_ffmpeg() -> dict[str, str]:
    candidates = [
        os.environ.get("SOFTWARE_DEMO_FFMPEG"),
        "/opt/homebrew/bin/ffmpeg",
        shutil.which("ffmpeg"),
        "/usr/local/bin/ffmpeg",
    ]
    seen: set[str] = set()
    failures: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        path = str(Path(candidate).expanduser())
        if path in seen or not os.access(path, os.X_OK):
            continue
        seen.add(path)
        probe = subprocess.run(
            [path, "-hide_banner", "-encoders"], capture_output=True, text=True
        )
        encoders = probe.stdout + probe.stderr
        try:
            selected = select_encoders(encoders)
        except RuntimeError as exc:
            failures.append(f"{path}: {exc}")
            continue
        adjacent = str(Path(path).with_name("ffprobe"))
        ffprobe = adjacent if os.access(adjacent, os.X_OK) else (shutil.which("ffprobe") or "")
        if not ffprobe:
            failures.append(f"{path}: ffprobe missing")
            continue
        return {"ffmpeg": path, "ffprobe": ffprobe, **selected}
    raise RuntimeError("No usable FFmpeg toolchain: " + "; ".join(failures))


def probe_media(path: Path, ffprobe: str | None = None) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size <= 0:
        raise RuntimeError(f"Media missing or empty: {path}")
    tool = ffprobe or resolve_ffmpeg()["ffprobe"]
    return run_json([
        tool,
        "-v", "error",
        "-show_entries", "format=duration,size,format_name",
        "-show_entries", "stream=duration,index,codec_name,codec_type,width,height,r_frame_rate,sample_rate,channels",
        "-of", "json",
        str(path),
    ])


def _unknown_keys(obj: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = set(obj) - allowed
    if unknown:
        raise ContractError(f"Unknown keys at {where}: {sorted(unknown)}")


def validate_json_schema(instance: Any, schema: dict[str, Any], path: str = "$") -> None:
    expected = schema.get("type")
    if expected:
        type_ok = {
            "object": isinstance(instance, dict),
            "array": isinstance(instance, list),
            "string": isinstance(instance, str),
            "integer": isinstance(instance, int) and not isinstance(instance, bool),
            "number": isinstance(instance, (int, float)) and not isinstance(instance, bool),
            "boolean": isinstance(instance, bool),
            "null": instance is None,
        }.get(expected, False)
        if not type_ok:
            raise ContractError(f"{path}: expected {expected}")
    if "const" in schema and instance != schema["const"]:
        raise ContractError(f"{path}: value does not match const")
    if "enum" in schema and instance not in schema["enum"]:
        raise ContractError(f"{path}: value not in enum")

    if isinstance(instance, dict):
        required = set(schema.get("required", []))
        missing = required - set(instance)
        if missing:
            raise ContractError(f"{path}: missing keys {sorted(missing)}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = set(instance) - set(properties)
            if unknown:
                raise ContractError(f"{path}: unknown keys {sorted(unknown)}")
        for key, value in instance.items():
            if key in properties:
                validate_json_schema(value, properties[key], f"{path}.{key}")

    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            raise ContractError(f"{path}: too few items")
        if schema.get("uniqueItems"):
            normalized = [json.dumps(value, sort_keys=True, ensure_ascii=False) for value in instance]
            if len(normalized) != len(set(normalized)):
                raise ContractError(f"{path}: items must be unique")
        item_schema = schema.get("items")
        if item_schema:
            for index, value in enumerate(instance):
                validate_json_schema(value, item_schema, f"{path}[{index}]")

    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            raise ContractError(f"{path}: string too short")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            raise ContractError(f"{path}: pattern mismatch")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if not math.isfinite(instance):
            raise ContractError(f"{path}: non-finite number")
        if "minimum" in schema and instance < schema["minimum"]:
            raise ContractError(f"{path}: below minimum")
        if "maximum" in schema and instance > schema["maximum"]:
            raise ContractError(f"{path}: above maximum")
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            raise ContractError(f"{path}: below exclusive minimum")


def validate_edit_spec(spec: dict[str, Any]) -> None:
    _unknown_keys(spec, {"version", "output", "source_provenance", "scenes"}, "root")
    required = {"version", "output", "source_provenance", "scenes"}
    if not required <= set(spec):
        raise ContractError(f"Missing root keys: {sorted(required - set(spec))}")
    if spec["version"] != "software-demo-video.edit-spec/v1":
        raise ContractError("Unsupported edit-spec version")

    output = spec["output"]
    if not isinstance(output, dict):
        raise ContractError("output must be an object")
    output_keys = {"width", "height", "fps", "audio_sample_rate", "filename"}
    _unknown_keys(output, output_keys, "output")
    if set(output) != output_keys:
        raise ContractError(f"output keys must equal {sorted(output_keys)}")
    if output["fps"] not in {24, 25, 30, 50, 60}:
        raise ContractError("Unsupported fps")
    if output["audio_sample_rate"] not in {32000, 44100, 48000}:
        raise ContractError("Unsupported audio sample rate")
    if "/" in output["filename"] or "\\" in output["filename"] or not output["filename"].endswith(".mp4"):
        raise ContractError("output filename must be an MP4 basename")

    provenance_ids: set[str] = set()
    for index, item in enumerate(spec["source_provenance"]):
        _unknown_keys(item, {"id", "label", "level", "checked_at"}, f"source_provenance[{index}]")
        if set(item) != {"id", "label", "level", "checked_at"}:
            raise ContractError(f"Incomplete source_provenance[{index}]")
        if item["id"] in provenance_ids:
            raise ContractError(f"Duplicate provenance id: {item['id']}")
        provenance_ids.add(item["id"])

    scenes = spec["scenes"]
    if not isinstance(scenes, list) or not scenes:
        raise ContractError("scenes must be a non-empty list")
    scene_ids: set[str] = set()
    allowed_scene = {
        "id", "title", "narration", "fact_refs", "visuals", "captions",
        "overlay", "base_scale", "transform_origin", "masks",
    }
    for index, scene in enumerate(scenes):
        _unknown_keys(scene, allowed_scene | {"camera", "clicks"}, f"scenes[{index}]")
        if not allowed_scene <= set(scene):
            raise ContractError(f"Incomplete scenes[{index}]")
        keys = scene.get("camera", [])
        if any(keys[i]["t"] >= keys[i + 1]["t"] for i in range(len(keys) - 1)):
            raise ContractError("camera keyframes must have strictly increasing times")
        if scene["id"] in scene_ids:
            raise ContractError(f"Duplicate scene id: {scene['id']}")
        scene_ids.add(scene["id"])
        if scene["overlay"] not in {"none", "search", "success"}:
            raise ContractError(f"Invalid overlay in {scene['id']}")
        missing_refs = set(scene["fact_refs"]) - provenance_ids
        if missing_refs:
            raise ContractError(f"Unknown fact refs in {scene['id']}: {sorted(missing_refs)}")
        if not scene["visuals"] or not scene["captions"] or not scene["narration"].strip():
            raise ContractError(f"Scene content missing in {scene['id']}")
        for visual in scene["visuals"]:
            _unknown_keys(visual, {"source", "start", "duration", "playback_rate"}, f"{scene['id']}.visuals")
            if not all(math.isfinite(float(visual.get(k, 1))) for k in ("start", "duration", "playback_rate")) or not 0.25 <= visual.get("playback_rate", 1) <= 4 or visual["start"] < 0 or visual["duration"] <= 0:
                raise ContractError(f"Invalid visual timing in {scene['id']}")
        last_end = 0.0
        for caption in scene["captions"]:
            _unknown_keys(caption, {"start", "end", "text"}, f"{scene['id']}.captions")
            if caption["start"] < last_end or caption["end"] <= caption["start"]:
                raise ContractError(f"Invalid caption timing in {scene['id']}")
            last_end = float(caption["end"])
        for mask in scene["masks"]:
            _unknown_keys(mask, {"x", "y", "width", "height", "color"}, f"{scene['id']}.masks")
            if mask["width"] <= 0 or mask["height"] <= 0:
                raise ContractError(f"Invalid mask in {scene['id']}")


def load_edit_spec(path: Path) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ContractError("Edit spec root must be an object")
    schema_path = Path(__file__).resolve().parent.parent / "schemas" / "edit-spec.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validate_json_schema(spec, schema)
    validate_edit_spec(spec)
    return spec


def resolve_source(spec_path: Path, source: str) -> Path:
    path = Path(source).expanduser()
    return path.resolve() if path.is_absolute() else (spec_path.parent / path).resolve()
