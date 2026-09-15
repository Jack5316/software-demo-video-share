#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from _common import sha256_file


DEFAULT_FORBIDDEN = [
    "覆盖当前草稿", "permission", "允许访问", "Screen Recording", "录屏工具栏",
    "输入密码", "验证码", "Delete permanently", "永久删除",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed screenshot gate with AX or an explicit AX limitation.")
    ax_input = parser.add_mutually_exclusive_group(required=True)
    ax_input.add_argument("--ax-text", type=Path)
    ax_input.add_argument("--ax-unavailable", metavar="REASON", help="Why AX is unavailable; requires screenshot-based source verification.")
    parser.add_argument("--screenshot", type=Path, required=True)
    parser.add_argument("--verdict", type=Path, required=True)
    parser.add_argument("--expected-source", action="append", default=[])
    parser.add_argument("--forbid", action="append", default=[])
    args = parser.parse_args()

    screenshot = args.screenshot.expanduser().resolve()
    reasons: list[str] = []
    ax_sha = None
    if args.ax_text:
        ax_path = args.ax_text.expanduser().resolve()
        ax_text = ax_path.read_text(encoding="utf-8", errors="replace")
        for source in args.expected_source:
            if source not in ax_text:
                reasons.append(f"expected source absent: {source}")
        for marker in DEFAULT_FORBIDDEN + args.forbid:
            if re.search(re.escape(marker), ax_text, re.I):
                reasons.append(f"forbidden AX marker: {marker}")
        ax_sha = sha256_file(ax_path)
    screenshot_sha = sha256_file(screenshot)
    verdict = json.loads(args.verdict.read_text(encoding="utf-8"))
    if verdict.get("ax_sha256") != ax_sha or verdict.get("screenshot_sha256") != screenshot_sha:
        reasons.append("verdict hash mismatch")
    if args.ax_unavailable is not None:
        if not args.ax_unavailable.strip() or verdict.get("ax_unavailable_reason") != args.ax_unavailable:
            reasons.append("AX unavailability reason missing or mismatched")
        if verdict.get("screenshot_controls") != "PASS":
            reasons.append("screenshot-based control calibration not verified")
        if not args.expected_source or verdict.get("verified_sources") != args.expected_source:
            reasons.append("expected sources must be explicitly verified in screenshot verdict")
    for field in ["status", "correct_state", "privacy", "no_modal", "no_permission_prompt", "geometry"]:
        if verdict.get(field) != "PASS":
            reasons.append(f"verdict field not PASS: {field}")
    if not verdict.get("reviewed_at") or not verdict.get("reviewer"):
        reasons.append("review metadata incomplete")

    result = {"status": "PASS" if not reasons else "FAIL", "ax_sha256": ax_sha, "ax_unavailable_reason": args.ax_unavailable, "screenshot_sha256": screenshot_sha, "reasons": reasons}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not reasons else 2


if __name__ == "__main__":
    raise SystemExit(main())
