# Edit spec contract

The schema of record is `schemas/edit-spec.schema.json` (`software-demo-video.edit-spec/v1`). Reject unknown fields.

## Minimal example

```json
{
  "version": "software-demo-video.edit-spec/v1",
  "output": {
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "audio_sample_rate": 48000,
    "filename": "demo.mp4"
  },
  "source_provenance": [
    {"id": "policy", "label": "Policy document", "level": "L1", "checked_at": "2026-08-27"}
  ],
  "scenes": [
    {
      "id": "scene-01",
      "title": "Open the source",
      "narration": "Open the source document.",
      "fact_refs": ["policy"],
      "visuals": [{"source": "raw/navigation.mov", "start": 1.0, "duration": 4.0}],
      "captions": [{"start": 0.0, "end": 3.8, "text": "Open the source document."}],
      "overlay": "none",
      "base_scale": 1.0,
      "transform_origin": "50% 50%",
      "masks": [{"x": 0, "y": 330, "width": 276, "height": 750, "color": "#f7f8fa"}]
    }
  ]
}
```

## Rules

- Resolve relative media paths against the spec directory. Preserve Unicode and spaces; never concatenate shell strings.
- Each scene represents one semantic action or result. `visuals` are ordered source intervals, with optional `playback_rate` (0.25–4, default 1), applied only to video. Effective length is duration / playback_rate. Sources must be in bounds. Overlong actions fail (one-frame quantization tolerance); select tighter intervals or an explicit readable rate. Shorter actions hold the last frame, recorded in materialization evidence. Never discard an action to fit speech.
- Narration is the MiniMax transmission boundary. Review sensitive text before TTS.
- Captions are scene-relative, ordered, non-overlapping, non-negative, and within final scene duration.
- `fact_refs` point to `source_provenance`; preserve exact numbers, thresholds, names, and qualifiers.
- Masks describe final-pixel treatment. Raw privacy scope remains determined by capture mode.
- `overlay` is `none`, `search`, or `success` in v1. Extend the schema before adding behavior.
- Final scene frames are derived from probed cue-audio duration, never hand-entered estimates.
