---
name: minimax-tts
description: >-
  Shared own-voice narration service for video and teaching skills. On a ready
  Apple Silicon MPS Mac prefer local OmniVoice with explicit sentence pauses;
  otherwise use the existing MiniMax clone, then key-free Edge TTS as the last
  fallback. Select once and pin each narration batch. Retains the
  legacy minimax-tts module/CLI names, with per-machine bootstrap and audio cache.
metadata:
  version: "2.1.3-share.1"
  domain: tts
---

# Shared cloned narration (legacy name: minimax-tts)

This is a sharing adaptation of upstream 2.1.3, prepared 2026-09-14. Supply your own authorized voice reference or cloud voice. No voice samples, profiles, account data or generated audio are included. Read ../README.md first. Choose and pin the provider explicitly for production; do not switch to a stock voice without the user's agreement.

Explicit user choices override auto routing (`VOICE_CLONE_PROVIDER` or
`provider="omnivoice"|"minimax"|"edge"`). A forced unavailable OmniVoice route errors.

## Prepare each machine, then generate

1. Before a production job, use `python3 scripts/setup_runtime.py --ensure`.
   It creates a native
   Python 3.11.15 under `~/.local/share/voice-clone/python` and a venv in
   `~/.local/share/voice-clone/venv` (not tied to another app runtime), installs compatible pinned
   torch/torchaudio/transformers and fixed OmniVoice source, and downloads a fixed
   official safetensors snapshot. Runtime/model files are local, never Git assets.
2. Private reference and profile live at `~/.config/voice-clone/reference.wav` and
   `profile.json`. Never
   put the reference, prompts, secrets, or generated voice caches into Skill Git.
   A missing/invalid reference means not ready; do not substitute voice.
3. `python3 scripts/setup_runtime.py` is a read-only readiness probe apart from its
   local status receipt. It verifies native arm64, actual MPS tensor arithmetic,
   available memory and encoders. Installation requires >=8 GiB free storage
   when creating a new runtime. On macOS, low current available RAM is a warning,
   not proof that the machine cannot run OmniVoice and not a routing veto. A ready
   MPS Mac stays local-first even while other apps occupy RAM. Keep the runtime
   installed; do not close user apps or lower PyTorch safety watermarks. Only an
   actual local failure/unsupported capability may trigger the documented fallback.
4. Setup also prepares an isolated `free-venv` with `edge-tts==7.2.8` on each host.
   Linux/Intel hosts skip heavy model installation and start with MiniMax. ffmpeg and
   ffprobe must exist for the video workflows. Missing Homebrew/permissions,
   voice references or credentials must be reported, never marked as successful setup.
   Setup logs/status: `~/.local/share/voice-clone/{status.json,worker.log}`.

`synthesize()` never installs packages or downloads models. Unready local runtime
falls back with a reason; prepare it outside the request before retrying.

## Compatible API

```python
from tts import begin_batch, synthesize, last_metadata
begin_batch()  # once per independent narration job, not once per cue
mp3 = synthesize(text="待配音文本", provider="auto", speed=1.0)
receipt = last_metadata()  # actual provider/model/reason/cache, no secrets
```

Existing `synthesize(text, voice_id, api_key, model, speed, volume, pitch,
pronunciation_dict, sample_rate, bitrate, timeout)` callers still receive MP3
bytes. `model` identifies the MiniMax fallback model; use `provider="minimax"`
when the user specifically wants to compare/use that cloud model. An explicitly
different voice ID or nonzero pitch selects cloud in auto mode. Local sample rate,
bitrate and volume are converted by FFmpeg to the requested output format.

Video and teaching skills must call this shared entry, not reproduce its routing
or credentials logic. Read the actual route once at the beginning; per-cue manual
engine verification is unnecessary.

Auto tries local OmniVoice when suitable (including Chinese narration), then the
existing MiniMax clone, then Edge TTS. Only failures before the first successful
audio may advance the fallback chain. Auto pins the provider after the first successful result in a batch/process.
An explicit provider selection starts a new independent provider scope.
First local failure may fall back before returning audio. Failure after local
results stops the job: retry locally or explicitly regenerate the whole job with
another provider. Do not silently mix engines in one narration. Explicit local-only
plans (`segments`) are not silently translated to cloud semantics.

MiniMax uses only `MINIMAX_TTS_API_KEY` and the existing `MINIMAX_VOICE_ID` with
`https://api.minimax.io/v1/t2a_v2`. Do not fall back to a different domestic key,
create new paid voices, or upload the local reference audio. Explicit MiniMax requests fail on API errors. Auto may fall through to Edge
before the first successful audio. Explicit custom voices, pitch or local segment
plans are not silently replaced by an incompatible free voice. Cloud key/voice ownership checks apply only to the cloud route.

## CLI and cue output

- `python3 scripts/tts_cli.py scripts.json out_dir` accepts a list of
  `{slug, script, pronunciation_dict?, provider?, speed?}` and writes MP3,
  `.duration`, and `.route.json`.
- `python3 scripts/tts_cued.py spec.json out_dir --rpm 10` accepts
  `{slug, cues:[{id,text,speed?}], speed?, silence_gap_ms?, provider?}`; returns
  MP3 and `.cues.json` with actual engine metadata per cue. Cue boundaries must
  use measured audio durations, not estimated word counts.
- MiniMax calls are paced at least 7 seconds start-to-start by the shared service;
  local calls/cache hits must not wait for cloud RPM. Limits are account-wide;
  do not run cloud jobs in parallel to bypass them.

## Selecting a new reference recording

When the user supplies a long recording, first inspect coherent passages and the
upstream length guidance. OmniVoice recommends 3–10 seconds; this is not a reason
to repeatedly choose the 3-second minimum for easy transcription. Start with a representative continuous passage near the upper end of that range,
ending at natural boundaries. If testing a longer passage (for example 14–17
seconds), label it experimental, provide matching reference text, preserve its
length and compare using the same text/seed/steps/speed. A longer clip is not
proven better merely because it is longer. If transcription is uncertain, inspect
or choose a different complete passage rather than automatically shrinking to the
minimum. Keep the already approved default until the user chooses a replacement.

## Pauses, expression, pronunciation

- Preserve source/display text separately from spoken text. The shared normalizer
  handles known number/identifier readings, including 1080P → “幺零八零 P”.
- OmniVoice uses the same fixed reference throughout a job. Split complete
  sentences and insert explicit gaps: period/exclamation 450 ms, question 550 ms,
  blank-line paragraph 800 ms; trim only quiet outer edges with safety padding.
  Disable internal silence compression. Do not later delete the inserted gaps.
- Plan semantic breaks across the whole narration, especially parallel variable
  definitions, enumerated data, and condition/conclusion changes. Distinct definitions
  such as “用 p 表示票价。用 N 表示人数。” should be separate sentences so the
  shared local service inserts measurable pauses. A comma alone is not proof of a
  timed gap. Keep a single formula, number, or tightly connected clause intact.
  Other backends need their supported cue/gap path when exact pauses are required;
  do not promise that punctuation alone forces a duration.
- Local metadata `segments` indexes the native worker waveform; use
  `segment_sample_rate` with `start_sample`, `end_sample`, and `pause_samples`.
  `sample_rate` separately describes the returned audio encoding.
- Context plans can pass `segments=[{text,speed,pause_ms}, ...]` to local synthesis.
  Joined segment text must match the normalized narration. Plan the full document
  once. Keep normal sentences intact; split only meaningful emphasis/contrast
  phrases. Native speed/duration are not exact emotion or word-stress controls.
- Do not pass arbitrary “happy/serious/emphasize this word” instructions. The
  installed model has a fixed attribute allowlist. Unsupported emotion, pitch or
  performance requirements require a tested compatible route, not invented tags.
- MiniMax pronunciation entries `word/replacement` are applied in spoken-text
  preprocessing for OmniVoice; the private profile can add local pinyin fixes.
  Clear user pronunciation instructions are already authorized. Only genuinely
  ambiguous new terms need a short targeted listening check, not fixed A/B/C gates.
- ASR may normalize pronunciations. Transcription accuracy and speaker embeddings
  are not human listening scores. Check new audio content and known trouble words.

## Efficiency and cache

One worker is reused within a calling process, with a 90-second idle shutdown and
exit cleanup. New batches re-probe resources when no worker is resident; changing
the private reference/profile refreshes the encoded voice prompt before generation.
Actual MPS availability is checked before model loading; CPU fallback is
disabled. Transient low available RAM is advisory, not a permanent capability limit. Private hashed caches include engine/code/model, reference/profile,
spoken text, pronunciation and speed. Validate file hashes, never only filenames.
Pauses are excluded from segment-audio identity so a pause-only edit only remuxes;
changed text/speed generates only affected speech. Unchanged verified audio can
reuse its content check, but new audio remains review-pending. Report generation,
checking and whole-job time separately. Do not extrapolate cache latency to new text.

## Security and license boundary

Vetted source: `08be0b4ccbac3e13e374e86fbfead4b4cac343e2`; model snapshot:
`c5fdb5ccb189668d56333f77ba2629f4cd7535f4`. No trust_remote_code. Source is Apache
2.0, but its bundled Higgs tokenizer has the Boson community license with additional
commercial/distribution conditions. Do not claim the entire stack unrestricted.
Compatible torch/torchaudio 2.11 requires setuptools<82: the pinned setuptools 81
and torch 2.11 retain published advisories affecting paths outside this selected
inference flow; this is not an all-CVE-cleared install. Do not load untrusted JIT,
checkpoints, archives or pickle prompts. Reassess compatible upgrades before
changing pins; installation success alone is not security verification.

## Key-free fallback

Edge TTS uses Microsoft Edge's online speech service through the `edge-tts`
project; it needs network access but no API key. It is not a local engine or
a voice clone. Default stock voice: `zh-CN-XiaoxiaoNeural` for Chinese,
`en-US-AriaNeural` for English; `EDGE_TTS_VOICE` can choose another supported
voice. The selected stock voice is held for the batch. Prepare with
`setup_runtime.py --ensure`; a successful import is not a service-availability
test. A real short synthesis verifies the network route. If it also fails,
return a clear error; never substitute silence. Explicit phoneme/pitch/local
segment controls unsupported by the free route stop rather than being discarded.

Primary implementation reference (checked 2026-09-13):
https://github.com/rany2/edge-tts

句内语义停顿：写逐字稿时同时标明需要停顿的从句边界，尤其“每变化一个单位，结果变化多少”一类定义。显示文本保留正常逗号；对理解至关重要的句内逗号，通过共享入口的 `segments` / `pause_ms` 显式执行（通常 350–500 ms），不能只验证句末停顿。仅在语义边界分段，不逐逗号切割公式或数字。用户指出连读时，只重配受影响句子并核验该边界的真实时间间隔。
