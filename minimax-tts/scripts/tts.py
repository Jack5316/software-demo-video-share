"""Shared narration boundary: local clone, cloud clone, key-free stock fallback.

All callers receive MP3 bytes. Routing and batch pinning live here, not in
video/teaching orchestrators. Legacy public module and function names remain.
"""
import json
import html
import hashlib
import time
import math
import sys
import threading
import os
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path

try:
    from pronunciation import merge_pronunciation_dict, apply_text_replacements
except ImportError:
    # 如果被当模块导入（非 CLI 同目录），尝试相对路径
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from pronunciation import merge_pronunciation_dict, apply_text_replacements


API_URL = "https://api.minimax.io/v1/t2a_v2"
DEFAULT_MODEL = "speech-02-hd"
DEFAULT_SAMPLE_RATE = 32000
DEFAULT_BITRATE = 128000

ERROR_CODES = {
    1039: "TPM 限流，稍后重试或检查订阅额度",
    2049: "域名/key 不匹配 — 国际版 key 必须用 api.minimax.io；如用了 MINIMAX_API_KEY（国内版）会报此错，改为 MINIMAX_TTS_API_KEY",
    2054: "voice_id 不属于当前账号 — 需重新克隆声音或换账号",
}


def load_secrets():
    """从 ~/.config/voice-clone/secrets.env 加载环境变量（如果该文件存在）。"""
    secrets = Path("~/.config/voice-clone/secrets.env").expanduser()
    if not secrets.exists():
        return
    for line in secrets.read_text().splitlines():
        m = re.match(r'export\s+(\w+)=["\']?([^"\']*)["\']?', line.strip())
        if m and m.group(1) not in os.environ:
            os.environ[m.group(1)] = m.group(2)


def _minimax_synthesize(
    text: str,
    voice_id: str = None,
    api_key: str = None,
    model: str = DEFAULT_MODEL,
    speed: float = 1.0,
    volume: float = 1.0,
    pitch: int = 0,
    pronunciation_dict: list = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    bitrate: int = DEFAULT_BITRATE,
    timeout: int = 120,
    _preprocessed: bool = False,
) -> bytes:
    """合成 MP3。返回原始 bytes。

    Args:
        text: 待合成文本（已做过 TEXT_REPLACEMENTS 预处理，或由 caller 在外层调 apply_text_replacements）
        voice_id: 默认取 $MINIMAX_VOICE_ID
        api_key: 默认取国际版 $MINIMAX_TTS_API_KEY
        pronunciation_dict: caller 追加的发音条目，会与全局字典合并
    """
    load_secrets()
    api_key = api_key or os.environ.get("MINIMAX_TTS_API_KEY")
    voice_id = voice_id or os.environ.get("MINIMAX_VOICE_ID")
    if not api_key:
        raise RuntimeError("MINIMAX_TTS_API_KEY 未设置（~/.config/voice-clone/secrets.env 或 env 里都没有）")
    if not voice_id:
        raise RuntimeError("MINIMAX_VOICE_ID 未设置")

    full_dict = merge_pronunciation_dict(pronunciation_dict)

    payload = {
        "model": model,
        "text": text if _preprocessed else apply_text_replacements(html.unescape(text)),
        "stream": False,
        "voice_setting": {"voice_id": voice_id, "speed": speed, "vol": volume, "pitch": pitch},
        "audio_setting": {"sample_rate": sample_rate, "bitrate": bitrate, "format": "mp3", "channel": 1},
    }
    if full_dict:
        payload["pronunciation_dict"] = {"tone": full_dict}

    req = urllib.request.Request(API_URL, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req, timeout=timeout) as r:
        j = json.loads(r.read())

    if j.get("base_resp", {}).get("status_code") == 0 and isinstance(j.get("data"), dict) and j["data"].get("audio"):
        return bytes.fromhex(j["data"]["audio"])

    # 错误处理：带友好提示
    base = j.get("base_resp", {})
    code = base.get("status_code", -1)
    msg = base.get("status_msg", str(j))
    hint = ERROR_CODES.get(code, "")
    raise RuntimeError(f"MiniMax API error {code}: {msg}" + (f" — {hint}" if hint else ""))


# Legacy module/CLI names retained; all callers share this routing boundary.
sys.path.insert(0, str(Path(__file__).parent))
import voice_runtime as _runtime
_MINIMAX_LOCK = threading.Lock()
_LAST_CLOUD_START = 0.0
_EDGE_BATCH_VOICE = None

def _record_result(metadata):
    global _EDGE_BATCH_VOICE
    if metadata['provider']=='edge':_EDGE_BATCH_VOICE=metadata['model']
    first = _runtime.selected_provider() is None
    _runtime.set_result(metadata)
    if first:
        print('[voice-clone] Batch route: '+json.dumps({k:metadata.get(k) for k in
            ['provider','model','reason','voice_kind']},ensure_ascii=False),file=sys.stderr,flush=True)


def _edge_voice(text):
    return _EDGE_BATCH_VOICE or os.getenv('EDGE_TTS_VOICE') or ('zh-CN-XiaoxiaoNeural' if re.search(r'[\u3400-\u9fff]',text) else 'en-US-AriaNeural')


def _edge_synthesize(text,speed,volume,sample_rate,bitrate,timeout,pronunciation_dict):
    py = _runtime.BASE/'free-venv/bin/python'
    if not py.is_file():
        raise RuntimeError('Free TTS runtime unavailable; run setup_runtime.py --ensure')
    for entry in merge_pronunciation_dict(pronunciation_dict):
        source, sep, target = entry.partition('/')
        if sep and source in text:
            if '(' in target or ')' in target:
                raise ValueError('Free TTS cannot preserve phoneme pronunciation controls')
            text=text.replace(source,target)
    with tempfile.TemporaryDirectory(prefix='edge-',dir=_runtime.BASE) as temp:
        raw=Path(temp)/'raw.mp3';output=Path(temp)/'audio.mp3'
        spec=dict(text=text,voice=_edge_voice(text),speed=speed,output=str(raw))
        result=subprocess.run([str(py),str(Path(__file__).with_name('edge_worker.py'))],
            input=json.dumps(spec),text=True,capture_output=True,timeout=timeout)
        if result.returncode:raise RuntimeError('Edge TTS service failed')
        result=subprocess.run([_runtime.find_command('ffmpeg'),'-v','error','-y','-i',str(raw),
            '-af','volume='+str(volume),'-ar',str(sample_rate),'-ac','1','-b:a',str(bitrate),str(output)],capture_output=True,timeout=60)
        if result.returncode:raise RuntimeError('Edge TTS audio conversion failed')
        return output.read_bytes()


def last_metadata():
    return _runtime.last_metadata()

def begin_batch():
    global _EDGE_BATCH_VOICE
    _EDGE_BATCH_VOICE=None
    _runtime.begin_batch()

def provider_status(provider=None, voice_id=None):
    load_secrets()
    selected, reason = _runtime.select_provider(provider, voice_id)
    return {"provider": selected, "reason": reason, "local": _runtime.local_status() if selected == "omnivoice" else None}

def synthesize(text, voice_id=None, api_key=None, model=DEFAULT_MODEL, speed=1.0,
               volume=1.0, pitch=0, pronunciation_dict=None, sample_rate=DEFAULT_SAMPLE_RATE,
               bitrate=DEFAULT_BITRATE, timeout=120, provider=None, segments=None):
    """Shared narration: MPS OmniVoice, MiniMax clone, then key-free Edge TTS.

    provider='minimax' or 'omnivoice' forces the requested backend. auto never
    mixes providers after the first successful result in this batch/process.
    Run setup_runtime.py --ensure separately; synthesis never installs packages.
    """
    global _LAST_CLOUD_START
    load_secrets()
    requested=provider or os.getenv('VOICE_CLONE_PROVIDER','auto')
    if requested in ['omnivoice','minimax','edge'] and _runtime.selected_provider() not in (None,requested):
        begin_batch()  # changing an explicit backend starts a new provider scope
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Nonempty narration text is required")
    if not math.isfinite(speed) or not .5 <= speed <= 2:
        raise ValueError("speed must be finite and between 0.5 and 2")
    if not math.isfinite(volume) or not 0 < volume <= 10:
        raise ValueError("volume must be finite and between 0 and 10")
    clean = apply_text_replacements(html.unescape(text))
    if segments is not None:
        segments = [dict(segment, text=apply_text_replacements(html.unescape(segment['text']))) for segment in segments]
    selected, reason = _runtime.select_provider(provider, voice_id, pitch)
    for entry in merge_pronunciation_dict(pronunciation_dict):
        src, sep, dst = entry.partition('/')
        if selected=='omnivoice' and sep and src in clean and ('(' in dst or ')' in dst) and not re.fullmatch(r'(?:\([A-Za-züÜvV]+[1-5]\))+',dst):
            if (provider or os.getenv('VOICE_CLONE_PROVIDER','auto'))=='omnivoice':
                raise ValueError('Unsupported local pronunciation; supply supported local pinyin/phonemes')
            selected, reason = 'minimax', 'local_pronunciation_unsupported'
    previous = _runtime.selected_provider()
    if previous in ['minimax','edge'] and (provider or os.getenv('VOICE_CLONE_PROVIDER','auto')) == 'auto':
        selected, reason = previous, 'batch_pinned_'+previous
    if previous and selected != previous:
        raise RuntimeError("Provider would change within a batch; regenerate the whole batch with an explicit provider")
    fingerprint = {'provider':selected, 'text':clean, 'voice':voice_id or os.getenv('MINIMAX_VOICE_ID'),
                   'model':model, 'speed':speed, 'volume':volume, 'pitch':pitch,
                   'cloud_account_fingerprint':hashlib.sha256((api_key or os.getenv('MINIMAX_TTS_API_KEY','')).encode()).hexdigest() if selected=='minimax' else None,
                   'pronunciation':merge_pronunciation_dict(pronunciation_dict),
                   'sample_rate':sample_rate, 'bitrate':bitrate, 'segments':segments,
                   'cache_schema':2}
    if selected=='edge':
        fingerprint.update(edge_voice=_edge_voice(clean),edge_worker_sha256=hashlib.sha256(Path(__file__).with_name('edge_worker.py').read_bytes()).hexdigest())
    if selected == 'omnivoice':
        fingerprint['profile_sha256'] = hashlib.sha256((_runtime.CONFIG/'profile.json').read_bytes()).hexdigest()
        fingerprint['reference_sha256'] = hashlib.sha256((_runtime.CONFIG/'reference.wav').read_bytes()).hexdigest()
        fingerprint['worker_sha256'] = hashlib.sha256(Path(__file__).with_name('omnivoice_worker.py').read_bytes()).hexdigest()
    digest = hashlib.sha256(json.dumps(fingerprint,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    cache = _runtime.BASE/'mp3-cache';cache.mkdir(parents=True,exist_ok=True,mode=0o700)
    cached = cache/(digest+'.mp3');record = cache/(digest+'.json')
    if cached.exists() and record.exists():
        try:meta=json.loads(record.read_text())
        except (ValueError,OSError):meta={}
        if hashlib.sha256(cached.read_bytes()).hexdigest()==meta.get('sha256'):
            metadata=meta['generation'];metadata['request_cache_hit']=True;metadata['original_processing_seconds']=metadata.get('processing_seconds');metadata['processing_seconds']=0
            metadata.setdefault('reason',reason);metadata.setdefault('voice_kind','stock' if selected=='edge' else 'cloned')
            _record_result(metadata);return cached.read_bytes()
    def save(audio,metadata):
        import tempfile
        with tempfile.NamedTemporaryFile(dir=cache,delete=False) as f:
            f.write(audio);temp=Path(f.name)
        temp.replace(cached)
        with tempfile.NamedTemporaryFile(mode='w',dir=cache,delete=False) as f:
            f.write(json.dumps({'sha256':hashlib.sha256(audio).hexdigest(),'generation':metadata},ensure_ascii=False));temporary_meta=Path(f.name)
        temporary_meta.replace(record)
        metadata.setdefault('reason',reason);metadata.setdefault('voice_kind','stock' if metadata['provider']=='edge' else 'cloned')
        _record_result(metadata)
    if selected == 'omnivoice':
        if previous is None and _runtime.local_status().get('memory_pressure_warning'):
            print('[voice-clone] MPS local selected; currently low available memory may slow generation.', file=sys.stderr)
        try:
            audio, metadata = _runtime.local_synthesize(clean, speed, volume,
                merge_pronunciation_dict(pronunciation_dict), sample_rate, bitrate, timeout, segments)
            save(audio, metadata)
            return audio
        except Exception as exc:
            if (provider or os.getenv('VOICE_CLONE_PROVIDER','auto')) == 'omnivoice' or previous == 'omnivoice':
                raise RuntimeError("Local synthesis failed; no mixed-provider output. Retry or explicitly restart the batch on MiniMax.") from exc
            selected, reason = 'minimax', 'local_failure_' + type(exc).__name__
    if segments is not None:
        raise ValueError("Explicit segment plans require OmniVoice; choose a cloud-compatible plan before fallback")
    requested=provider or os.getenv('VOICE_CLONE_PROVIDER','auto')
    if selected=='minimax':
        try:
            with _MINIMAX_LOCK:
                time.sleep(max(0, 7 - (time.monotonic() - _LAST_CLOUD_START)))
                _LAST_CLOUD_START = time.monotonic()
                audio = _minimax_synthesize(clean, voice_id, api_key, model, speed, volume, pitch,
                                           pronunciation_dict, sample_rate, bitrate, timeout, _preprocessed=True)
            metadata={'provider':'minimax','model':model,'reason':reason,'voice_kind':'cloned','output_format':'mp3','sample_rate':sample_rate}
            if fingerprint['provider']=='minimax':save(audio,metadata)
            else:_record_result(metadata)
            return audio
        except Exception as exc:
            if requested!='auto' or previous is not None:
                raise RuntimeError('MiniMax synthesis failed; batch route unchanged. Retry or explicitly restart the whole batch.') from exc
            if pitch or (voice_id and voice_id!=os.getenv('MINIMAX_VOICE_ID')):
                raise RuntimeError('Free TTS cannot preserve the requested voice/pitch') from exc
            selected,reason='edge',str(reason)+';minimax_failure_'+type(exc).__name__
    if selected=='edge':
        if voice_id and voice_id!=os.getenv('MINIMAX_VOICE_ID'):
            raise ValueError('Free TTS cannot preserve the requested custom voice')
        if pitch:raise ValueError('Free TTS does not preserve MiniMax pitch controls')
        audio=_edge_synthesize(clean,speed,volume,sample_rate,bitrate,timeout,pronunciation_dict)
        metadata={'provider':'edge','model':_edge_voice(clean),'reason':reason,'voice_kind':'stock',
                  'output_format':'mp3','sample_rate':sample_rate,'network_required':True}
        if fingerprint['provider']=='edge':save(audio,metadata)
        else:_record_result(metadata)
        return audio
    raise RuntimeError('No usable narration provider')
