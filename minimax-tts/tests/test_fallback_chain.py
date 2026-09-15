import unittest,tempfile,pathlib,sys,os,io
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import tts,voice_runtime as r

class FallbackChain(unittest.TestCase):
 def setUp(self):
  tts.begin_batch();self.tmp=tempfile.TemporaryDirectory();self.base=pathlib.Path(self.tmp.name)
  (self.base/'profile.json').write_text('{}');(self.base/'reference.wav').write_bytes(b'ref')
  self.stack=[]
  for target,kwargs in [(tts,{'load_secrets':lambda:None}), (r,{'BASE':self.base,'CONFIG':self.base})]:
   for key,value in kwargs.items():
    p=patch.object(target,key,value);p.start();self.stack.append(p)
  p=patch.dict(os.environ,{},clear=True);p.start();self.stack.append(p)
  p=patch.object(tts.time,'sleep');p.start();self.stack.append(p)
 def tearDown(self):
  for p in reversed(self.stack):p.stop()
  tts.begin_batch();self.tmp.cleanup()
 def test_ready_local_never_calls_cloud_or_free(self):
  with patch.object(r,'local_status',return_value={'local_ready':True}),patch.object(r,'local_synthesize',return_value=(b'local',{'provider':'omnivoice','model':'local'})),patch.object(tts,'_minimax_synthesize') as cloud,patch.object(tts,'_edge_synthesize') as free:
   self.assertEqual(tts.synthesize('中文'),b'local');cloud.assert_not_called();free.assert_not_called()
 def test_initial_failures_reach_free_and_pin_once(self):
  out=io.StringIO()
  with patch.object(r,'local_status',return_value={'local_ready':True}),patch.object(r,'local_synthesize',side_effect=RuntimeError('local failed')) as local,patch.object(tts,'_minimax_synthesize',side_effect=RuntimeError('cloud failed')) as cloud,patch.object(tts,'_edge_synthesize',return_value=b'free') as free,patch('sys.stderr',out):
   self.assertEqual(tts.synthesize('中文第一句'),b'free');self.assertEqual(tts.synthesize('下一句'),b'free')
   self.assertEqual(r.selected_provider(),'edge');self.assertEqual(local.call_count,1);self.assertEqual(cloud.call_count,1);self.assertEqual(free.call_count,2);self.assertEqual(out.getvalue().count('Batch route:'),1)
   self.assertEqual(tts.last_metadata()['voice_kind'],'stock');self.assertEqual(tts._edge_voice('English'),'zh-CN-XiaoxiaoNeural')
 def test_mid_batch_cloud_failure_cannot_switch_to_free(self):
  r.set_result({'provider':'minimax'})
  with patch.object(tts,'_minimax_synthesize',side_effect=RuntimeError('failure')),patch.object(tts,'_edge_synthesize') as free:
   with self.assertRaisesRegex(RuntimeError,'batch route unchanged'):tts.synthesize('中文')
   free.assert_not_called()
 def test_explicit_minimax_never_falls_back(self):
  with patch.object(tts,'_minimax_synthesize',side_effect=RuntimeError('failure')),patch.object(tts,'_edge_synthesize') as free:
   with self.assertRaises(RuntimeError):tts.synthesize('中文',provider='minimax')
   free.assert_not_called()
 def test_auto_custom_voice_is_not_replaced_by_stock(self):
  with patch.object(tts,'_minimax_synthesize',side_effect=RuntimeError('failure')),patch.object(tts,'_edge_synthesize') as free:
   with self.assertRaisesRegex(RuntimeError,'requested voice'):tts.synthesize('中文',voice_id='different')
   free.assert_not_called()
 def test_cache_has_actual_provider(self):
  with patch.object(r,'local_status',return_value={'local_ready':False,'reason':'non_mps'}),patch.object(tts,'_minimax_synthesize',side_effect=RuntimeError('failure')),patch.object(tts,'_edge_synthesize',return_value=b'free'):
   tts.synthesize('第一句');tts.synthesize('第二句')
  import json
  receipts=[json.loads(p.read_text()) for p in (self.base/'mp3-cache').glob('*.json')]
  self.assertEqual(len(receipts),1);self.assertEqual(receipts[0]['generation']['provider'],'edge')


 def test_explicit_edge_keeps_first_voice_across_cues(self):
  with patch.object(tts,'_edge_synthesize',return_value=b'free'):
   tts.synthesize('中文',provider='edge');tts.synthesize('English',provider='edge')
   self.assertEqual(tts.last_metadata()['model'],'zh-CN-XiaoxiaoNeural')
 def test_pinned_local_rejects_new_custom_voice(self):
  r.set_result({'provider':'omnivoice'})
  with self.assertRaisesRegex(RuntimeError,'cannot be silently discarded'):r.select_provider('auto','different')
 def test_explicit_edge_rejects_custom_voice(self):
  with patch.object(tts,'_edge_synthesize') as free:
   with self.assertRaisesRegex(ValueError,'custom voice'):tts.synthesize('中文',provider='edge',voice_id='different')
   free.assert_not_called()
 def test_unrelated_phoneme_does_not_disable_edge(self):
  import json,subprocess
  py=self.base/'free-venv/bin/python';py.parent.mkdir(parents=True);py.touch()
  def fake_run(cmd,**kwargs):
   if 'input' in kwargs:Path=pathlib.Path;Path(json.loads(kwargs['input'])['output']).write_bytes(b'raw')
   else:pathlib.Path(cmd[-1]).write_bytes(b'encoded')
   return subprocess.CompletedProcess(cmd,0)
  with patch.object(tts.subprocess,'run',side_effect=fake_run):
   self.assertEqual(tts._edge_synthesize('普通测试',1,1,32000,128000,120,['罕见/(han3)(jian4)']),b'encoded')

if __name__=='__main__':unittest.main()
