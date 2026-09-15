"""Regression checks for real action preservation and honest probe reporting."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _common import ContractError, load_edit_spec, probe_media, resolve_ffmpeg, sha256_file
from materialize_project import cue_map, render_visual


class ActionTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="software-demo-action-test-")
        cls.directory = Path(cls.temp.name)
        cls.media = resolve_ffmpeg()
        cls.source = cls.directory / "真实动作 test.mp4"
        # Red preparation followed by green completed state. Checking decoded
        # pixels verifies that speed/hold preserves the result, not just length.
        subprocess.run([
            cls.media["ffmpeg"], "-y", "-v", "error", "-f", "lavfi", "-i",
            "color=red:s=160x90:r=30:d=1", "-f", "lavfi", "-i",
            "color=lime:s=160x90:r=30:d=1", "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]",
            "-c:v", cls.media["encoder"], "-pix_fmt", "yuv420p", str(cls.source),
        ], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def render(self, visuals, target, name):
        output = self.directory / name
        receipt = render_visual(self.media["ffmpeg"], self.media["encoder"], visuals,
                                self.directory / "spec.json", target, 160, 90, 30, output)
        return output, receipt

    def pixel(self, video, seconds):
        result = subprocess.run([
            self.media["ffmpeg"], "-v", "error", "-ss", str(seconds), "-i", str(video),
            "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ], check=True, capture_output=True)
        self.assertEqual(len(result.stdout), 3)
        return tuple(result.stdout)

    def test_noninteger_speed_preserves_result_and_last_frame_hold(self):
        output, receipt = self.render([{"source": str(self.source), "start": 0,
                                        "duration": 2, "playback_rate": 1.5}], 2, "rate-hold.mp4")
        self.assertAlmostEqual(receipt[0]["effective_duration"], 4 / 3)
        self.assertAlmostEqual(float(probe_media(output)["format"]["duration"]), 2, delta=1 / 30)
        early = self.pixel(output, .2)
        result = self.pixel(output, 1.8)
        self.assertGreater(early[0], early[1] + 100)
        self.assertGreater(result[1], result[0] + 100)

    def test_overlong_action_refuses_silent_truncation(self):
        with self.assertRaisesRegex(ValueError, "refusing silent truncation"):
            self.render([{"source": str(self.source), "start": 0, "duration": 2}], 1, "rejected.mp4")
        self.assertFalse((self.directory / "rejected.mp4").exists())

    def test_source_interval_beyond_media_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "source range"):
            self.render([{"source": str(self.source), "start": 1.8, "duration": .5}], 1, "out-of-range.mp4")

    def test_longer_audio_cannot_extend_visual_source_bounds(self):
        mixed = self.directory / "long-audio.mp4"
        subprocess.run([
            self.media["ffmpeg"], "-y", "-v", "error", "-i", str(self.source),
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-map", "0:v:0",
            "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", str(mixed),
        ], check=True)
        self.assertGreater(float(probe_media(mixed)["format"]["duration"]), 3)
        with self.assertRaisesRegex(ValueError, "source range"):
            self.render([{"source": str(mixed), "start": 2.5, "duration": .5}], 1, "audio-tail.mp4")

    def test_multiple_intervals_preserve_order_and_final_state(self):
        output, receipt = self.render([
            {"source": str(self.source), "start": 0, "duration": .6, "playback_rate": 1.5},
            {"source": str(self.source), "start": 1, "duration": .6, "playback_rate": .75},
        ], 2, "multi-range.mp4")
        self.assertAlmostEqual(sum(v["effective_duration"] for v in receipt), 1.2)
        early, later = self.pixel(output, .1), self.pixel(output, 1.8)
        self.assertGreater(early[0], early[1] + 100)
        self.assertGreater(later[1], later[0] + 100)

    def test_rate_bounds_and_nonfinite_values_fail_spec_validation(self):
        for rate in [0, .1, 4.1, float("nan"), float("inf")]:
            with self.subTest(rate=rate):
                spec = json.loads((ROOT / "tests/fixtures/minimal-edit-spec.json").read_text())
                spec["scenes"][0]["visuals"][0]["playback_rate"] = rate
                path = self.directory / "invalid-spec.json"
                path.write_text(json.dumps(spec))
                with self.assertRaises(ContractError):
                    load_edit_spec(path)

    def test_incomplete_or_nonfinite_cue_is_rejected(self):
        for cue in [{"id": "a", "start": 0, "end": 1, "extra": True},
                    {"id": "a", "start": 0, "end": float("nan"), "text": "test"}]:
            with self.subTest(cue=cue):
                path = self.directory / "invalid-cues.json"
                path.write_text(json.dumps({"cues": [cue]}))
                with self.assertRaises(ValueError):
                    cue_map(path)

    def test_media_probe_is_not_end_to_end_proof(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/preflight.py"), "--json",
                                 "--recording-evidence", str(self.source)], capture_output=True, text=True)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ready"]["recording_media_probe_verified"])
        self.assertFalse(payload["ready"]["end_to_end_verified"])

    def test_ax_unavailable_requires_explicit_pixel_source_review(self):
        screenshot = self.directory / "pre-take.png"
        subprocess.run([self.media["ffmpeg"], "-y", "-v", "error", "-i", str(self.source),
                        "-frames:v", "1", str(screenshot)], check=True)
        reason = "Target exposes no accessible UI tree"
        verdict = {key: "PASS" for key in ["status", "correct_state", "privacy", "no_modal",
                                          "no_permission_prompt", "geometry", "screenshot_controls"]}
        verdict.update(ax_sha256=None, screenshot_sha256=sha256_file(screenshot),
                       ax_unavailable_reason=reason, verified_sources=["Synthetic red state"],
                       reviewed_at="2026-09-06", reviewer="synthetic-test")
        path = self.directory / "pre-take-verdict.json"
        command = [sys.executable, str(ROOT / "scripts/pre_take_gate.py"), "--ax-unavailable", reason,
                   "--screenshot", str(screenshot), "--verdict", str(path),
                   "--expected-source", "Synthetic red state"]
        path.write_text(json.dumps(verdict))
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIsNone(json.loads(result.stdout)["ax_sha256"])
        for field, replacement in [("verified_sources", []), ("ax_unavailable_reason", ""),
                                   ("screenshot_controls", "FAIL"), ("ax_sha256", "fabricated")]:
            with self.subTest(field=field):
                broken = dict(verdict)
                broken[field] = replacement
                path.write_text(json.dumps(broken))
                rejected = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(rejected.returncode, 2, rejected.stdout + rejected.stderr)


if __name__ == "__main__":
    unittest.main()
