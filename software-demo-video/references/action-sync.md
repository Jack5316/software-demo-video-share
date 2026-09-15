# Transcript-led action synchronization

Use one short semantic unit per edit-spec scene: open a panel, enter a request, submit, inspect a result. Keep stable scene IDs shared with TTS cues. The scene narration bytes anchor the transcript; the materializer checks cue-text equality and records narration hashes. Preserve raw recordings privately.

Before operating, record application/version, verified window selector, user-authorized scope, starting state, semantic control descriptions, expected resulting state and chosen coordinate space. Re-read AX after actions; indices are transient. If unavailable, inspect current pixels and record the calibrated target. Code may record/time/render, but must not manufacture an app interaction history.

After recording, map each unit to observed source start/duration. Tool call timestamps only locate candidate frames; verify actual visible transitions. Remove preparation/waits first; mark removed waits in tutorial narration or captions. Choose a readable explicit playback_rate if needed. Do not turn long AI waits into a false instant result.

The materializer computes final scene frames from actual narration audio, enforces source bounds and rejects effective visuals exceeding the speech slot. It emits rate/effective duration and `hold_last_seconds`. Final scene positions are cumulative scene frames, not original concatenated TTS positions (padding changes them). Check scene audio against individual source cues; if the shared TTS concatenation has padding/drift, rebuild a decoded PCM concatenation with recalculated cue times before materialization.

For timing-risk units save a brief review row when useful: id, narration hash, source interval/rate, final start/end, hold, visible action timestamp, related phrase, PASS/issue. A small duration difference does not prove semantic sync. Retake only the affected action; fixed narration is reused unless its text changes. User-supplied original audio is a separate preservation task: this TTS-oriented renderer splits/re-encodes and must not be represented as an untouched original-voice workflow.

`hold_last_seconds` is derived from selected intervals and rates, not a decoded measurement. Check final video duration and boundary frames; resampling each interval can introduce frame rounding, especially with many source intervals. The final review records observed action times and any quantization discrepancy.

Observed in the 2026-09-06 WorkBuddy case: AAC/container padding accumulated about 0.35 seconds across 19 scenes. Burned captions and audio remained together, but external SRT offsets based only on nominal frame counts drifted. Use measured rendered-container/final join timing for SRT and inspect a late join; do not redo TTS or review every frame to fix this.
