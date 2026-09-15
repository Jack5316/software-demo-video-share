#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from _common import ContractError, load_edit_spec, select_encoders, sha256_file, validate_edit_spec  # noqa: E402


class ContractTests(unittest.TestCase):
    def fixture(self) -> dict:
        return json.loads((ROOT / "tests" / "fixtures" / "minimal-edit-spec.json").read_text())

    def test_valid_fixture(self) -> None:
        validate_edit_spec(self.fixture())

    def test_optional_motion_and_invalid_order(self):
        spec=self.fixture()
        spec['scenes'][0]['camera']=[{'t':0,'scale':1,'x':.5,'y':.5},{'t':1,'scale':1.5,'x':.6,'y':.8}]
        spec['scenes'][0]['clicks']=[{'t':.5,'x':.7,'y':.8,'label':'verified click'}]
        validate_edit_spec(spec)
        spec['scenes'][0]['camera'].reverse()
        with self.assertRaises(ContractError):validate_edit_spec(spec)

    def test_unknown_key_fails_closed(self) -> None:
        spec = self.fixture()
        spec["unexpected"] = True
        with self.assertRaises(ContractError):
            validate_edit_spec(spec)

    def test_overlapping_captions_fail(self) -> None:
        spec = self.fixture()
        spec["scenes"][0]["captions"].append({"start": 0.5, "end": 0.9, "text": "Overlap"})
        with self.assertRaises(ContractError):
            validate_edit_spec(spec)

    def test_declared_json_schema_constraints_are_enforced(self) -> None:
        mutations = [
            ("width", lambda spec: spec["output"].update(width=1)),
            ("provenance", lambda spec: spec["source_provenance"][0].update(level="NOT_A_LEVEL")),
            ("scale", lambda spec: spec["scenes"][0].update(base_scale=99)),
        ]
        for label, mutate in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                spec = self.fixture()
                mutate(spec)
                path = Path(temp) / "spec.json"
                path.write_text(json.dumps(spec))
                with self.assertRaises(ContractError):
                    load_edit_spec(path)

    def test_encoder_fallback_selection(self) -> None:
        self.assertEqual(select_encoders("h264_videotoolbox libmp3lame")["encoder"], "h264_videotoolbox")
        self.assertEqual(select_encoders("libx264 h264_videotoolbox libmp3lame")["encoder"], "libx264")
        with self.assertRaises(RuntimeError):
            select_encoders("h264_videotoolbox")

    def test_preflight_does_not_leak_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            secret = Path(temp) / "secrets.zsh"
            api_key_name = "MINIMAX_" + "TTS_API_KEY"
            voice_name = "MINIMAX_" + "VOICE_ID"
            secret.write_text(f'export {api_key_name}="DO_NOT_PRINT_ME"\nexport {voice_name}="PRIVATE_VOICE"\n')
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "preflight.py"), "--json", "--secrets", str(secret)],
                capture_output=True, text=True,
            )
            self.assertNotIn("DO_NOT_PRINT_ME", proc.stdout + proc.stderr)
            self.assertNotIn("PRIVATE_VOICE", proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["configuration"]["MINIMAX_TTS_API_KEY"])
            self.assertTrue(payload["configuration"]["MINIMAX_VOICE_ID"])

    def test_missing_secrets_are_reported_without_disclosure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            secret = Path(temp) / "empty.zsh"
            secret.write_text("")
            env = dict(os.environ)
            env.pop("MINIMAX_TTS_API_KEY", None)
            env.pop("MINIMAX_VOICE_ID", None)
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "preflight.py"), "--json", "--secrets", str(secret)],
                capture_output=True, text=True, env=env,
            )
            payload = json.loads(proc.stdout)
            self.assertFalse(payload["configuration"]["MINIMAX_TTS_API_KEY"])
            self.assertFalse(payload["configuration"]["MINIMAX_VOICE_ID"])

    def test_tts_spec_preserves_scene_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            spec_path = Path(temp) / "edit spec.json"
            out = Path(temp) / "tts spec.json"
            spec_path.write_text(json.dumps(self.fixture(), ensure_ascii=False))
            subprocess.run([sys.executable, str(SCRIPTS / "make_tts_spec.py"), str(spec_path), str(out)], check=True)
            payload = json.loads(out.read_text())
            self.assertEqual(payload["cues"][0]["id"], "scene-01")
            self.assertEqual(payload["cues"][0]["text"], "Synthetic narration.")

    def test_synthetic_fixture_contains_unicode_and_space_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            subprocess.run([sys.executable, str(SCRIPTS / "synthetic_fixture.py"), temp], check=True, capture_output=True)
            payload = json.loads((Path(temp) / "edit-spec.json").read_text())
            source = payload["scenes"][0]["visuals"][0]["source"]
            self.assertIn("导航", source)
            self.assertIn(" ", source)

    def test_stale_cue_text_and_missing_media_fail_materialization(self) -> None:
        if not Path("/opt/homebrew/bin/ffmpeg").exists():
            self.skipTest("Homebrew FFmpeg missing")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run([sys.executable, str(SCRIPTS / "synthetic_fixture.py"), str(root)], check=True, capture_output=True)
            spec_path = root / "edit-spec.json"
            original = json.loads(spec_path.read_text())
            stale = json.loads(json.dumps(original))
            stale["scenes"][0]["narration"] = "Changed narration with the same cue id."
            spec_path.write_text(json.dumps(stale))
            proc = subprocess.run([
                sys.executable, str(SCRIPTS / "materialize_project.py"),
                "--spec", str(spec_path), "--cues", str(root / "cues.json"),
                "--combined-audio", str(root / "combined narration.mp3"), "--output", str(root / "stale-project"),
            ], capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("cue text does not match narration", proc.stderr)

            missing = json.loads(json.dumps(original))
            missing["scenes"][0]["visuals"][0]["source"] = "raw clips/does-not-exist.mp4"
            spec_path.write_text(json.dumps(missing))
            proc = subprocess.run([
                sys.executable, str(SCRIPTS / "materialize_project.py"),
                "--spec", str(spec_path), "--cues", str(root / "cues.json"),
                "--combined-audio", str(root / "combined narration.mp3"), "--output", str(root / "missing-project"),
            ], capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("visual source missing", proc.stderr)

    def _fake_recorder(self, root: Path, sleep_seconds: float, create_media: bool) -> Path:
        script = root / "fake-recorder"
        script.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env python3
            import subprocess, sys, time
            time.sleep({sleep_seconds})
            output = sys.argv[-1]
            if {create_media!r}:
                subprocess.run(['/opt/homebrew/bin/ffmpeg','-y','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=30','-t','1','-c:v','libx264','-pix_fmt','yuv420p',output], check=True)
        """))
        script.chmod(0o755)
        return script

    def test_recorder_ready_and_natural_completion(self) -> None:
        if not Path("/opt/homebrew/bin/ffmpeg").exists():
            self.skipTest("Homebrew FFmpeg missing")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = self._fake_recorder(root, 0.85, True)
            output = root / "take.mov"
            proc = subprocess.run([
                sys.executable, str(SCRIPTS / "record_segment.py"),
                "--seconds", "1", "--ready-delay", "0.1", "--screencapture", str(fake),
                "--output", str(output),
            ], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            events = [json.loads(line)["event"] for line in proc.stdout.splitlines() if line.strip()]
            self.assertEqual(events, ["READY", "COMPLETED"])

    def test_interrupted_recorder_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = self._fake_recorder(root, 10, False)
            output = root / "take.mov"
            proc = subprocess.Popen([
                sys.executable, str(SCRIPTS / "record_segment.py"),
                "--seconds", "3", "--ready-delay", "0.1", "--screencapture", str(fake),
                "--output", str(output),
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            ready = proc.stdout.readline()
            self.assertEqual(json.loads(ready)["event"], "READY")
            proc.send_signal(signal.SIGINT)
            stdout, stderr = proc.communicate(timeout=5)
            self.assertEqual(proc.returncode, 130, stdout + stderr)
            self.assertIn('"event": "REJECTED"', stdout)

    def test_timed_out_recorder_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = self._fake_recorder(root, 10, False)
            proc = subprocess.run([
                sys.executable, str(SCRIPTS / "record_segment.py"),
                "--seconds", "1", "--ready-delay", "0.1", "--timeout", "0.4",
                "--screencapture", str(fake), "--output", str(root / "take.mov"),
            ], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 6, proc.stdout + proc.stderr)
            self.assertIn('"reason": "timeout"', proc.stdout)

    def test_modal_state_is_rejected_by_pre_take_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ax = root / "state.txt"
            screenshot = root / "screen.png"
            verdict = root / "verdict.json"
            ax.write_text("WorkBuddy 覆盖当前草稿？")
            screenshot.write_bytes(b"synthetic screenshot")
            verdict.write_text(json.dumps({
                "ax_sha256": sha256_file(ax), "screenshot_sha256": sha256_file(screenshot),
                "status": "PASS", "correct_state": "PASS", "privacy": "PASS",
                "no_modal": "PASS", "no_permission_prompt": "PASS", "geometry": "PASS",
                "reviewed_at": "2026-08-27T12:00:00+08:00", "reviewer": "test",
            }))
            proc = subprocess.run([
                sys.executable, str(SCRIPTS / "pre_take_gate.py"),
                "--ax-text", str(ax), "--screenshot", str(screenshot), "--verdict", str(verdict),
            ], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("forbidden AX marker", proc.stdout)

    def test_package_audit_rejects_generated_media(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "bad.skill"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("demo/SKILL.md", "---\nname: demo\ndescription: demo\n---\n")
                archive.writestr("demo/raw.mp4", b"not media")
            proc = subprocess.run([
                sys.executable, str(SCRIPTS / "audit_package.py"), str(package),
            ], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("forbidden generated/media file", proc.stdout)


if __name__ == "__main__":
    unittest.main()
