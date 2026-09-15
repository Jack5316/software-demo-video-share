import json,sys,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pronunciation,tts
class SpokenNumbers(unittest.TestCase):
 def test_resolution_reading_and_idempotence(self):
  for text in ['1080P','1080p','1080 P']:
   self.assertEqual(pronunciation.apply_text_replacements(text),'幺零八零 P')
  self.assertEqual(pronunciation.apply_text_replacements('幺零八零 P'),'幺零八零 P')
 def test_ordinary_quantities_and_larger_identifiers_unchanged(self):
  text='1080元、1080页、21080P、model1080p、1080P_test'
  self.assertEqual(pronunciation.apply_text_replacements(text),text)
 def test_direct_synthesis_cannot_skip_normalization(self):
  response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps({'base_resp':{'status_code':0},'data':{'audio':'00'}}).encode()
  with patch.object(tts,'load_secrets'),patch.object(tts.urllib.request,'urlopen',return_value=response) as request:
   self.assertEqual(tts._minimax_synthesize('分辨率为1080P。',api_key='<test-key>',voice_id='test-voice'),b'\x00')
   body=json.loads(request.call_args.args[0].data)
   self.assertEqual(body['text'],'分辨率为幺零八零 P。')
if __name__=='__main__':unittest.main()
