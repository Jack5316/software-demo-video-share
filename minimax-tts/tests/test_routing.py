import unittest,sys,pathlib,os
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import tts,voice_runtime as r
class Routing(unittest.TestCase):
 def setUp(self):r.begin_batch();r._probe=None
 def test_non_mps_auto_cloud(self):
  with patch.object(r,'local_status',return_value={'local_ready':False,'reason':'non_mps_platform'}):self.assertEqual(r.select_provider('auto')[0],'minimax')
 def test_explicit_local_fails_without_mps(self):
  with patch.object(r,'local_status',return_value={'local_ready':False,'reason':'non_mps_platform'}):
   with self.assertRaises(RuntimeError):r.select_provider('omnivoice')
 def test_ready_local_needs_no_cloud_key(self):
  with patch.dict(os.environ,{},clear=True),patch.object(r,'local_status',return_value={'local_ready':True}):self.assertEqual(r.select_provider('auto')[0],'omnivoice')
 def test_other_voice_and_pitch_preserved(self):
  with patch.dict(os.environ,{'MINIMAX_VOICE_ID':'own'}):
   self.assertEqual(r.select_provider('auto','another')[0],'minimax')
   self.assertEqual(r.select_provider('auto','own',pitch=2)[0],'minimax')
 def test_mixed_provider_rejected(self):
  r.set_result({'provider':'omnivoice'})
  with patch.object(r,'select_provider',return_value=('minimax','unavailable')):
   with self.assertRaisesRegex(RuntimeError,'Provider would change'):tts.synthesize('测试')
 def test_bad_speed_never_calls_backend(self):
  with self.assertRaises(ValueError):tts.synthesize('测试',speed=float('nan'))
 def test_provider_metadata_no_fake_ready(self):
  with patch.object(r,'select_provider',return_value=('minimax','runtime_not_installed')):self.assertEqual(tts.provider_status()['reason'],'runtime_not_installed')

 def test_explicit_provider_resets_old_scope(self):
  import tempfile,json
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);(p/'profile.json').write_text('{}');(p/'reference.wav').write_bytes(b'reference')
   r.set_result({'provider':'minimax'})
   with patch.object(r,'CONFIG',p),patch.object(r,'BASE',p),patch.object(r,'select_provider',return_value=('omnivoice','ready')),patch.object(r,'local_synthesize',return_value=(b'audio',{'provider':'omnivoice'})):
    self.assertEqual(tts.synthesize('独立任务',provider='omnivoice'),b'audio')
 def test_protocol_noise_closes_worker(self):
  import tempfile,io
  from unittest.mock import MagicMock
  worker=MagicMock();worker.poll.return_value=None;worker.stdin=io.StringIO();worker.stdout=io.StringIO('noise from native library\n')
  with tempfile.TemporaryDirectory() as d,patch.object(r,'BASE',pathlib.Path(d)),patch.object(r,'_worker',worker),patch.object(r.select,'select',return_value=([worker.stdout],[],[])),patch.object(r,'close_worker') as close:
   with self.assertRaisesRegex(RuntimeError,'invalid_worker_protocol'):r.local_synthesize('测试',1,1,[],24000,128000,2)
   close.assert_called_once()


 def test_new_batch_rechecks_previously_low_memory(self):
  r._probe={'local_ready':False,'reason':'insufficient_available_memory'}
  with patch.object(r,'_worker',None):r.begin_batch();self.assertIsNone(r._probe)
 def test_reference_switch_refreshes_encoded_prompt(self):
  import ast
  from unittest.mock import MagicMock
  source=(pathlib.Path(__file__).resolve().parents[1]/'scripts/omnivoice_worker.py').read_text()
  node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='ensure_prompt')
  namespace={'model':MagicMock(),'prompt':None,'prompt_signature':None,'CONFIG':pathlib.Path('/private/reference')}
  exec(compile(ast.Module(body=[node],type_ignores=[]),'<worker function>','exec'),namespace)
  fn=namespace['ensure_prompt'];fn({'reference_text':'原参考'},'hash-a');fn({'reference_text':'原参考'},'hash-a');self.assertEqual(namespace['model'].create_voice_clone_prompt.call_count,1)
  fn({'reference_text':'新参考'},'hash-b');self.assertEqual(namespace['model'].create_voice_clone_prompt.call_count,2)


 def test_low_free_ram_does_not_veto_ready_mps_mac(self):
  with patch.object(r,'local_status',return_value={'local_ready':True,'memory_pressure_warning':True,'available_memory':3*1024**3}):
   self.assertEqual(r.select_provider('auto')[0],'omnivoice')

if __name__=='__main__':unittest.main()
