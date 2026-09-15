#!/usr/bin/env python3
"""Idempotent per-machine runtime preparation. No heavy packages on non-MPS hosts."""
import argparse,json,os,pathlib,platform,shutil,subprocess,sys,time,fcntl,hashlib
BASE=pathlib.Path.home()/'.local/share/voice-clone'
CONFIG=pathlib.Path.home()/'.config/voice-clone'
CODE_REV='08be0b4ccbac3e13e374e86fbfead4b4cac343e2'
MODEL_REV='c5fdb5ccb189668d56333f77ba2629f4cd7535f4'

def find_command(name):
 for p in [shutil.which(name),str(pathlib.Path.home()/'.local/bin'/name),'/opt/homebrew/bin/'+name,'/usr/local/bin/'+name,'/opt/miniconda3/bin/'+name]:
  if p and os.access(p,os.X_OK) and pathlib.Path(p).is_file():return p
 return None

def run(args,**kwargs):
 return subprocess.run(args,check=True,timeout=kwargs.pop('timeout',1200),**kwargs)

def prepare_free(ensure=False):
 py=BASE/'free-venv/bin/python'
 expected='7.2.8'
 def ready():
  if not py.is_file():return False
  try:
   return subprocess.check_output([str(py),'-c','import edge_tts,importlib.metadata; print(importlib.metadata.version("edge-tts"))'],text=True,timeout=15).strip()==expected
  except Exception:return False
 if ensure and not ready():
  if not py.exists():run([sys.executable,'-m','venv',str(BASE/'free-venv')])
  run([str(py),'-m','pip','install','edge-tts=='+expected],stdout=sys.stderr)
 return {'free_tts_ready':ready(),'free_tts_provider':'edge','free_tts_version':expected,'free_tts_network_verified':False}

def prepare(ensure=False):
 BASE.mkdir(parents=True,exist_ok=True,mode=0o700)
 status={'platform':platform.system(),'architecture':platform.machine(),'checked_at':time.time(),'local_ready':False}
 ff=find_command('ffmpeg');probe=find_command('ffprobe')
 if ensure and (not ff or not probe) and platform.system()=='Darwin':
  brew=find_command('brew')
  if brew:run([brew,'install','ffmpeg']);ff=find_command('ffmpeg');probe=find_command('ffprobe')
 if ensure and (not ff or not probe) and platform.system()=='Linux':
  apt=find_command('apt-get');sudo=find_command('sudo')
  prefix=[] if os.geteuid()==0 else ([sudo,'-n'] if sudo else None)
  if apt and prefix is not None:
   try:run(prefix+[apt,'install','-y','ffmpeg'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);ff=find_command('ffmpeg');probe=find_command('ffprobe')
   except Exception:pass
 status['ffmpeg_ready']=bool(ff and probe)
 try:status.update(prepare_free(ensure))
 except Exception as exc:status.update(free_tts_ready=False,free_tts_reason=type(exc).__name__)
 if platform.system()!='Darwin' or platform.machine()!='arm64':
  status.update(provider='minimax',reason='non_mps_platform');return status
 py=BASE/'venv/bin/python'
 if not (CONFIG/'reference.wav').is_file() or not (CONFIG/'profile.json').is_file():
  status.update(provider='minimax',reason='missing_private_reference');return status
 if not py.exists() and not ensure:
  status.update(provider='minimax',reason='runtime_not_installed');return status
 if ensure:
  memory=int(subprocess.check_output(['sysctl','-n','hw.memsize']))
  status['physical_memory']=memory
  # Reserve storage for venv, model, download cache and temporary decode buffers.
  if not py.exists() and shutil.disk_usage(BASE).free<8*1024**3:
   status.update(provider='minimax',reason='less_than_8GiB_free_disk');return status
  own_uv=BASE/'bootstrap/bin/uv'
  uv=str(own_uv) if own_uv.exists() else find_command('uv')
  uv_version=subprocess.check_output([uv,'--version'],text=True).split()[1] if uv else None
  if not uv or uv_version!='0.12.9':
   bootstrap=BASE/'bootstrap'
   run([sys.executable,'-m','venv',str(bootstrap)])
   run([str(bootstrap/'bin/python'),'-m','pip','install','uv==0.12.9'])
   uv=str(bootstrap/'bin/uv')
  installed=BASE/'installed.json'
  expected={'code_revision':CODE_REV,'model_revision':MODEL_REV,'torch':'2.11.0','transformers':'5.17.0','setuptools':'81.0.0','private_python':'3.11.15','lock_sha256':hashlib.sha256(pathlib.Path(__file__).with_name('requirements-mps.lock').read_bytes()).hexdigest(),'schema':1}
  current=json.loads(installed.read_text()) if installed.exists() else {}
  model_path=pathlib.Path.home()/('.cache/huggingface/hub/models--k2-fsa--OmniVoice/snapshots/'+MODEL_REV)
  model_present=all((model_path/x).is_file() for x in ['model.safetensors','audio_tokenizer/model.safetensors','config.json','tokenizer.json'])
  if current!=expected or not py.exists() or not model_present or not str(py.resolve()).startswith(str(BASE/'python')):
   python_env=dict(os.environ,UV_PYTHON_INSTALL_DIR=str(BASE/'python'))
   run([uv,'python','install','3.11.15','--no-bin'],env=python_env)
   candidates=list((BASE/'python').glob('cpython-3.11.15-macos-aarch64-*/bin/python3.11'))
   if len(candidates)!=1:raise RuntimeError('private_native_python_not_found')
   private_python=candidates[0]
   if not py.exists():run([uv,'venv','--python',str(private_python),str(BASE/'venv')],env=python_env)
   else:
    # Supported venv upgrade keeps installed packages and fixed entry-point paths.
    run([str(private_python),'-m','venv','--upgrade','--without-pip',str(BASE/'venv')])
   # uv-created environments may retain their old executable symlinks on upgrade.
   for alias in ['python','python3','python3.11']:
    next_link=BASE/'venv/bin'/('.'+alias+'-next')
    next_link.unlink(missing_ok=True);next_link.symlink_to(private_python)
    next_link.replace(BASE/'venv/bin'/alias)
   run([uv,'pip','install','--python',str(py),'-r',str(pathlib.Path(__file__).with_name('requirements-mps.lock'))])
   # Download only data weights/configuration from a fixed official model revision.
   code='from huggingface_hub import snapshot_download; snapshot_download("k2-fsa/OmniVoice",revision='+repr(MODEL_REV)+',allow_patterns=["*.json","*.safetensors","*.txt","*.jinja","LICENSE","README.md"])'
   env=dict(os.environ,HF_HUB_DISABLE_TELEMETRY='1');run([str(py),'-c',code],env=env)
   installed.write_text(json.dumps(expected,indent=2))
 installed=BASE/'installed.json'
 lock_hash=hashlib.sha256(pathlib.Path(__file__).with_name('requirements-mps.lock').read_bytes()).hexdigest()
 if not installed.exists() or json.loads(installed.read_text()).get('lock_sha256')!=lock_hash or json.loads(installed.read_text()).get('private_python')!='3.11.15' or not str(py.resolve()).startswith(str(BASE/'python')):
  status.update(provider='minimax',reason='runtime_update_required');return status
 code='import torch,psutil,json;x=torch.ones(1,device="mps");y=(x+x).cpu().item();assert y==2;print(json.dumps({"mps":torch.backends.mps.is_available(),"available_memory":psutil.virtual_memory().available,"torch":torch.__version__}))'
 try:
  j=json.loads(subprocess.check_output([str(py),'-c',code],timeout=30,text=True))
  status.update(j)
  model_path=pathlib.Path.home()/('.cache/huggingface/hub/models--k2-fsa--OmniVoice/snapshots/'+MODEL_REV)
  model_present=all((model_path/x).is_file() for x in ['model.safetensors','audio_tokenizer/model.safetensors','config.json','tokenizer.json'])
  ready=j['mps'] and bool(ff) and model_present
  status['memory_pressure_warning']=j['available_memory']<6*1024**3
  reason='ready' if ready else ('model_files_missing' if not model_present else 'mps_or_encoder_unavailable')
  status.update(local_ready=ready,provider='omnivoice' if ready else 'minimax',reason=reason)
 except Exception as exc:status.update(provider='minimax',reason='runtime_probe_'+type(exc).__name__)
 return status

def main():
 p=argparse.ArgumentParser();p.add_argument('--ensure',action='store_true');a=p.parse_args()
 BASE.mkdir(parents=True,exist_ok=True,mode=0o700)
 with open(BASE/'setup.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  try:s=prepare(a.ensure)
  except Exception as e:s={'local_ready':False,'provider':'minimax','reason':'setup_'+type(e).__name__,'checked_at':time.time()}
  (BASE/'status.json').write_text(json.dumps(s,indent=2));print(json.dumps(s))
if __name__=='__main__':main()
