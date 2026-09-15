#!/usr/bin/env python3
"""Private persistent local worker; NDJSON stdin/stdout, no credentials or network."""
import os
os.environ['HF_HUB_OFFLINE']='1';os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
import contextlib,hashlib,json,pathlib,re,sys,time
# Reserve a dedicated protocol fd before importing native libraries.
_PROTOCOL=os.fdopen(os.dup(sys.stdout.fileno()), 'w', buffering=1)
os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
import numpy as np
import soundfile as sf
import torch
from omnivoice import OmniVoice
from setup_runtime import BASE,CONFIG,MODEL_REV,CODE_REV
SR=24000;CACHE=BASE/'audio-cache';CACHE.mkdir(parents=True,exist_ok=True,mode=0o700)
model=None;prompt=None;prompt_signature=None

def trim(a):
 a=np.asarray(a,dtype=np.float32).reshape(-1);w=240
 rms=np.array([np.sqrt(np.mean(a[i:i+w]**2)) for i in range(0,len(a),w)])
 on=np.flatnonzero(rms>10**(-50/20))
 if not len(on):raise ValueError('silent_audio')
 return a[max(0,int(on[0]*w)-1440):min(len(a),int((on[-1]+1)*w)+1440)].copy()

def ensure_prompt(cfg,refhash):
 global model,prompt,prompt_signature
 if model is None:
  if not torch.backends.mps.is_available():raise RuntimeError('mps_unavailable')
  torch.set_num_threads(min(6,os.cpu_count() or 1))
  model=OmniVoice.from_pretrained(str(pathlib.Path.home()/('.cache/huggingface/hub/models--k2-fsa--OmniVoice/snapshots/'+MODEL_REV)),device_map='mps',dtype=torch.float16,use_safetensors=True,attn_implementation='sdpa')
 signature=(refhash,cfg['reference_text'],cfg.get('preprocess_prompt',True))
 if prompt_signature!=signature:
  prompt=model.create_voice_clone_prompt(ref_audio=str(CONFIG/'reference.wav'),ref_text=cfg['reference_text'],preprocess_prompt=cfg.get('preprocess_prompt',True))
  prompt_signature=signature

def execute(req):
 global model,prompt
 cfg=json.loads((CONFIG/'profile.json').read_text());refhash=hashlib.sha256((CONFIG/'reference.wav').read_bytes()).hexdigest()
 if refhash!=cfg['reference_sha256']:raise ValueError('reference_hash_mismatch')
 segments=req.get('segments')
 if segments is None:
  segments=[]
  for para in re.split(r'\n\s*\n',req['text'].strip()):
   ss=[m.group().strip() for m in re.finditer(r'.+?(?:[。！？!?]+[”’」』】"]*|$)',para,re.S) if m.group().strip()]
   for i,s in enumerate(ss):segments.append({'text':s,'speed':req['speed'],'pause_ms':cfg['paragraph_pause_ms'] if i==len(ss)-1 else (cfg['question_pause_ms'] if re.search(r'[？?][”’」』】"]*$',s) else cfg['sentence_pause_ms'])})
  if segments:segments[-1]['pause_ms']=0
 if re.sub(r'\s+','',''.join(s['text'] for s in segments))!=re.sub(r'\s+','',req['text']):raise ValueError('segments_do_not_match_text')
 chunks=[];rows=[];hits=0;cursor=0;t=time.perf_counter()
 for s in segments:
  if not .5<=s['speed']<=2 or not 0<=s['pause_ms']<=5000:raise ValueError('invalid_segment_controls')
  text=s['text']
  for item in req['pronunciation_dict']:
   src,sep,dst=item.partition('/')
   if sep and src and src in text:
    if re.fullmatch(r'(?:\([A-Za-züÜvV]+[1-5]\))+',dst):dst=' '.join(re.findall(r'\(([^()]+)\)',dst)).upper()
    elif '(' in dst or ')' in dst:raise ValueError('unsupported_local_phoneme')
    text=text.replace(src,dst)
  for src,dst in cfg.get('local_pronunciation_overrides',{}).items():text=text.replace(src,dst)
  identity={'text':text,'speed':s['speed'],'steps':cfg['steps'],'seed':cfg['seed'],'ref':refhash,'reference_text':cfg['reference_text'],'preprocess_prompt':cfg.get('preprocess_prompt',True),'revision':MODEL_REV,'code_revision':CODE_REV,'worker_schema':3}
  key=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode()).hexdigest();f=CACHE/(key+'.wav');meta=CACHE/(key+'.json')
  cached=f.exists() and meta.exists() and json.loads(meta.read_text())['sha256']==hashlib.sha256(f.read_bytes()).hexdigest()
  if cached:a,rate=sf.read(f,dtype='float32');assert rate==SR;hits+=1
  else:
   ensure_prompt(cfg,refhash)
   torch.manual_seed(cfg['seed']);a=trim(model.generate(text=text,voice_clone_prompt=prompt,num_step=cfg['steps'],speed=s['speed'],postprocess_output=False)[0]);torch.mps.synchronize()
   tmp=f.with_suffix('.tmp.wav');sf.write(tmp,a,SR,subtype='FLOAT');tmp.replace(f);meta.write_text(json.dumps({'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'content_verification':'pending','identity':identity},ensure_ascii=False))
  if not np.isfinite(a).all():raise ValueError('nonfinite_audio')
  row={'start_sample':cursor,'end_sample':cursor+len(a),'cache_hit':cached,'text_sha256':hashlib.sha256(s['text'].encode()).hexdigest()};chunks.append(a);cursor+=len(a)
  silence=round(s['pause_ms']*SR/1000);chunks.append(np.zeros(silence,dtype=np.float32));row['pause_samples']=silence;cursor+=silence;rows.append(row)
 if not chunks:raise ValueError('empty_text')
 audio=np.concatenate(chunks);sf.write(req['wav_path'],audio,SR)
 return {'provider':'omnivoice','model':'k2-fsa/OmniVoice','revision':MODEL_REV,'device':'mps','duration_seconds':len(audio)/SR,'processing_seconds':time.perf_counter()-t,'cache_hits':hits,'segment_sample_rate':SR,'segments':rows,'new_audio_requires_content_check':hits<len(rows)}

for line in sys.stdin:
 req={}
 try:
  req=json.loads(line)
  with contextlib.redirect_stdout(sys.stderr):result=execute(req)
  print(json.dumps({'ok':True,'request_id':req['request_id'],'text_sha256':hashlib.sha256(req['text'].encode()).hexdigest(),'metadata':result}),file=_PROTOCOL,flush=True)
 except Exception as e:print(json.dumps({'ok':False,'request_id':req.get('request_id'),'error':type(e).__name__}),file=_PROTOCOL,flush=True)
