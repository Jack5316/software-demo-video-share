"""Independent regression checks for artifact reuse and its invalidation boundaries."""
import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('render_pipeline', Path(__file__).parents[1] / 'scripts/render_pipeline.py')
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


class CacheBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        for directory in ['src', 'scripts', 'public/audio', 'public/video']:
            (self.project / directory).mkdir(parents=True)
        (self.project / 'src/Scene.tsx').write_text('layout v1')
        (self.project / 'package-lock.json').write_text('runtime v1')
        self.plan = {'fps': 30, 'scenes': []}
        for sid in ['one', 'two']:
            self.plan['scenes'].append({'id': sid, 'audioFile': sid + '.mp3', 'videoFile': sid + '.mp4', 'captions': [{'text': sid}]})
            (self.project / 'public/audio' / (sid + '.mp3')).write_bytes(sid.encode())
            (self.project / 'public/video' / (sid + '.mp4')).write_bytes(sid.encode())

    def keys(self, plan=None):
        return pipeline.fingerprints(self.project, plan or self.plan)

    def test_unchanged_input_reuses_identical_key(self):
        self.assertEqual(self.keys(), self.keys(copy.deepcopy(self.plan)))

    def test_media_change_invalidates_only_affected_scene(self):
        before = self.keys()
        (self.project / 'public/video/one.mp4').write_bytes(b'changed')
        after = self.keys()
        self.assertNotEqual(before['one'], after['one'])
        self.assertEqual(before['two'], after['two'])

    def test_caption_change_invalidates_only_affected_scene(self):
        before = self.keys()
        self.plan['scenes'][0]['captions'][0]['text'] = 'changed'
        after = self.keys()
        self.assertNotEqual(before['one'], after['one'])
        self.assertEqual(before['two'], after['two'])

    def test_shared_layout_and_runtime_invalidate_all(self):
        for relative in ['src/Scene.tsx', 'package-lock.json']:
            before = self.keys()
            (self.project / relative).write_text('changed')
            after = self.keys()
            self.assertTrue(all(before[sid] != after[sid] for sid in before))

    def test_scene_order_invalidates_keys(self):
        before = self.keys()
        self.plan['scenes'].reverse()
        self.assertNotEqual(before, self.keys())

    def test_corrupted_or_missing_render_is_never_reused(self):
        output = self.project / 'render.mp4'
        output.write_bytes(b'original')
        receipt = {'key': 'input', 'sha256': pipeline.digest(output)}
        self.assertTrue(pipeline.reusable(receipt, 'input', output))
        self.assertFalse(pipeline.reusable(receipt, 'different', output))
        output.write_bytes(b'corrupt')
        self.assertFalse(pipeline.reusable(receipt, 'input', output))
        output.unlink()
        self.assertFalse(pipeline.reusable(receipt, 'input', output))


if __name__ == '__main__':
    unittest.main()
