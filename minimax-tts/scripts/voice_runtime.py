"""Provider routing and persistent local-worker transport (standard library only)."""
import atexit,hashlib,json,os,pathlib,platform,select,subprocess,tempfile,threading,time,uuid
from setup_runtime import BASE,CONFIG,find_command,prepare
_LOCK=threading.RLock();_worker=None;_last={};_probe=None;_selected=None;_idle=None

def last_metadata():return dict(_last)
def begin_batch():
 global _selected,_probe
 _selected=None
 if _worker is None or _worker.poll() is not None:_probe=None

def local_status(refresh=False):
 global _probe
 if refresh or _probe is None:
  _probe=prepare(False)
 return dict(_probe)

def select_provider(provider=None,voice_id=None,pitch=0):
 requested=provider or os.getenv('VOICE_CLONE_PROVIDER','auto')
 if requested not in ['auto','omnivoice','minimax','edge']:raise ValueError('Invalid voice provider')
 if requested=='auto' and _selected:
  if _selected in ['omnivoice','edge'] and (pitch or (voice_id and voice_id!=os.getenv('MINIMAX_VOICE_ID'))):
   raise RuntimeError('Provider would change within a batch; explicit voice/pitch cannot be silently discarded')
  return _selected,'batch_pinned_'+_selected
 if requested in ['minimax','edge']:return requested,'explicit'
 reason=None
 default=os.getenv('MINIMAX_VOICE_ID')
 if voice_id and voice_id!=default:reason='different_voice_requested'
 elif pitch:reason='local_pitch_control_unsupported'
 else:
  status=local_status();reason=None if status['local_ready'] else status.get('reason','local_not_ready')
 if reason and requested=='omnivoice':raise RuntimeError('OmniVoice unavailable: '+reason)
 return ('minimax',reason) if reason else ('omnivoice','mps_ready')

def close_worker():
 global _worker
 with _LOCK:
  if _worker is not None:
   if _worker.poll() is None:
    _worker.terminate()
    try:_worker.wait(timeout=5)
    except subprocess.TimeoutExpired:_worker.kill();_worker.wait()
   _worker=None
atexit.register(close_worker)

def _touch_idle():
 global _idle
 if _idle:_idle.cancel()
 _idle=threading.Timer(90,close_worker);_idle.daemon=True;_idle.start()

def local_synthesize(text,speed,volume,pronunciation_dict,sample_rate,bitrate,timeout,segments=None):
 global _worker
 with _LOCK:
  if _idle:_idle.cancel()
  if _worker is None or _worker.poll() is not None:
   BASE.mkdir(parents=True,exist_ok=True,mode=0o700)
   logfile=BASE/'worker.log'
   if logfile.exists() and logfile.stat().st_size>1048576:logfile.replace(BASE/'worker.previous.log')
   log=open(logfile,'a')
   env={k:v for k,v in os.environ.items() if k in ['HOME','PATH','LANG','LC_ALL','TMPDIR']}
   env.update(HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',PYTORCH_ENABLE_MPS_FALLBACK='0')
   _worker=subprocess.Popen([str(BASE/'venv/bin/python'),str(pathlib.Path(__file__).with_name('omnivoice_worker.py'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,env=env);log.close()
  with tempfile.TemporaryDirectory(prefix='tts-',dir=BASE) as tmp:
   wav=pathlib.Path(tmp)/'speech.wav';mp3=pathlib.Path(tmp)/'speech.mp3'
   request_id=uuid.uuid4().hex
   payload={'request_id':request_id,'text':text,'speed':speed,'pronunciation_dict':pronunciation_dict,'wav_path':str(wav),'segments':segments}
   _worker.stdin.write(json.dumps(payload,ensure_ascii=False)+'\n');_worker.stdin.flush()
   wait=max(timeout,min(1800,len(text)*.15))
   readable,_,_=select.select([_worker.stdout],[],[],wait)
   if not readable:close_worker();raise TimeoutError('local_generation_timeout')
   try:
    result=json.loads(_worker.stdout.readline())
    if result.get('request_id')!=request_id:raise ValueError('response_request_mismatch')
    if result.get('ok') and result.get('text_sha256')!=hashlib.sha256(text.encode()).hexdigest():raise ValueError('response_text_mismatch')
   except Exception:
    close_worker();raise RuntimeError('invalid_worker_protocol') from None
   if not result.get('ok'):close_worker();raise RuntimeError('local_worker_'+result.get('error','failed'))
   cmd=[find_command('ffmpeg'),'-v','error','-y','-i',str(wav),'-af','volume='+str(volume),'-ar',str(sample_rate),'-ac','1','-b:a',str(bitrate),str(mp3)]
   subprocess.run(cmd,check=True,timeout=60,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   data=mp3.read_bytes();metadata=result['metadata'];metadata['output_format']='mp3';metadata['sample_rate']=sample_rate
  _touch_idle();return data,metadata

def set_result(metadata):
 global _last,_selected
 _last=dict(metadata);_selected=metadata['provider']

def selected_provider():return _selected
