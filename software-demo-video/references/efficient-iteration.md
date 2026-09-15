# Efficient iteration without weakening final verification

Prepare source facts, action steps and the software environment before recording. Keep the recording interval for real UI operation; stop before writing code or reviewing files. For unpredictable app processing, stage captures or preserve a continuous take only when requested. No fixed turnaround promise follows from one WorkBuddy example.

## Preview first

After materialization, use `render_pipeline.py --project project --stage preview --scene ID --frame N` to render a still at N and up to three seconds around it. Without arguments the pipeline chooses the longest-caption scene and its midpoint. Inspect actual pixels and action transitions for caption/control overlap, scaling and masks. CSS changes are not evidence that a rendered layout changed. Choose another action scene when needed; don't use a cover-only preview for interaction layout.

The preview receipt hashes the inputs, still and clip. `--stage build --preview-reviewed` means the current caller really inspected those files; it is not user approval and never asks the user for routine layout review. Changed preview inputs/files are rejected. A representative preview saves iteration time; final visual checks focus on predicted risks, observed defects and affected edits.

## Reuse at the right boundary

| Change | Work required |
|---|---|
| Caption/style/overlay only | Edit the materialized scene plan/template, preview the affected layout, run the pipeline. Reuse audio bytes and previously established narration-content evidence. Final visual/privacy review is renewed. |
| Retained video intervals/rate | Re-materialize affected inputs using the existing materializer, preview changed actions, rebuild. The materializer currently rewrites all media; this pipeline does not claim to cache that step. |
| Narration text/voice/model/speed/pronunciation | Regenerate affected speech with matching configuration evidence, rebuild cues and dependent timing, then preview/build/verify. Never reuse voice solely because text matches. |
| Nothing changed | Pipeline checks input AND output hashes; reuse rendered scenes, concatenation and unchanged machine evidence. Reuse a final verdict only if every bound hash still matches. |

The cache lives in project/out/pipeline-cache.json, not the Skill. Shared source/template/config/lock/runtime changes invalidate all scenes; a scene-plan or its referenced audio/video change invalidates that scene. Scene order changes invalidate the composition context. A modified/deleted output invalidates its cache. With no trusted cache, the first build renders normally; do not manufacture receipts to skip it.

Machine QA is automatically chained after rendering/concatenation. Its receipt is not semantic/privacy approval: record the current owner’s risk-based review and use `qa_final.py --require-verdict` before delivery. After a changed final video, refresh bindings and selected evidence for affected risks; reuse byte-identical original-audio content checks only with final audio integrity/order/timing verification. No repeated voice synthesis or full ASR merely to test a CSS change.

Batch deterministic build steps in one tool call and return on failure. Independent review may overlap preparation or narration when authorized, but no two agents/recorders should control the same app or write the same project. Keep bounded progress updates; avoid status polling that cannot change the next decision.
