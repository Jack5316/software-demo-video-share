import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from qa_final import risk_points, reusable_frames, extract_samples
from unittest.mock import patch
from _common import sha256_file

class RiskSampling(unittest.TestCase):
    def test_small_baseline_does_not_scale_with_length(self):
        self.assertEqual(len(risk_points(4)), 3)
        self.assertEqual(len(risk_points(3600)), 3)

    def test_explicit_risks_and_duplicate_reasons_are_retained(self):
        points = risk_points(100, {'points':[{'time':20,'reason':'menu opens'}, {'time':20,'reason':'old leak'}]})
        self.assertEqual(len(points), 4)
        self.assertIn('old leak', points[1]['reason'])

    def test_invalid_or_unexplained_samples_fail(self):
        for t in [-1, 100, float('nan'), float('inf'), True]:
            with self.subTest(t=t), self.assertRaises(ValueError):
                risk_points(100, {'points':[{'time':t,'reason':'risk'}]})
        with self.assertRaises(ValueError):
            risk_points(100, {'points':[{'time':20,'reason':''}]})

    def test_empty_decode_cannot_pass_with_a_stale_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); folder=root/'sample-frames';folder.mkdir()
            stale=folder/'sample-0001.png';stale.write_bytes(b'old pixels')
            with patch('qa_final.subprocess.run'), self.assertRaises(FileNotFoundError):
                extract_samples(root/'video.mp4',[{'time':1,'reason':'near cut'}],root,'ffmpeg')
            self.assertFalse(stale.exists())

    def test_subtitle_only_edit_reuses_frames_but_tampering_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); f=root/'frame.png'; f.write_bytes(b'pixels')
            sampling={'mode':'risk','points':[{'time':1,'reason':'privacy'}]}
            hashes={'artifact_sha256':'video','scene_plan_sha256':'plan','srt_sha256':'new-subtitles'}
            manifest={**hashes,'srt_sha256':'old-subtitles','sampling':sampling,'qa_engine_sha256':'engine',
                      'evidence':[{'path':'frame.png','sha256':sha256_file(f)}]}
            self.assertTrue(reusable_frames(manifest,hashes,sampling,'engine',root))
            self.assertFalse(reusable_frames(manifest,{**hashes,'artifact_sha256':'changed'},sampling,'engine',root))
            self.assertFalse(reusable_frames(manifest,hashes,{'mode':'risk','points':[]},'engine',root))
            f.write_bytes(b'corrupted')
            self.assertFalse(reusable_frames(manifest,hashes,sampling,'engine',root))
            f.unlink()
            self.assertFalse(reusable_frames(manifest,hashes,sampling,'engine',root))

if __name__=='__main__': unittest.main()
