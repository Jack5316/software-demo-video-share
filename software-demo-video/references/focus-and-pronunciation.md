# Focused operation demos and natural terminology

Optional edit-spec fields:

```json
{"camera":[{"t":0,"scale":1,"x":0.5,"y":0.5},{"t":1,"scale":1.6,"x":0.62,"y":0.69},{"t":8,"scale":1.6,"x":0.62,"y":0.69},{"t":9,"scale":1,"x":0.5,"y":0.5}],"clicks":[{"t":1.12,"x":0.686,"y":0.927,"label":"open menu"}]}
```

Times are scene-relative seconds after retained-clip editing, not original recording time. x/y use normalized coordinates in the displayed video viewport (output height minus the 120px caption band), before camera transform. Values above illustrate the schema, not reusable app selectors. Camera times must increase; scale 1–2. Motion stays inside the viewport. Choose a bounded pull-in/hold/pull-out for a meaningful action, not constant cursor chasing. All camera motion is editorial framing, not an app action.

`FocusMotion.tsx` transforms media, privacy masks and click rings together. Captions/scene labels stay outside. Recheck a zoom extreme and a risky transition rather than all frames. Existing `base_scale` is static framing; masks must already match that base view before animated camera motion is added. The materializer keeps optional camera/click fields; older specs without them remain static.

Retain actual action coordinates/timestamps during future CUA recording where available, then calibrate against visible cuts. Existing recordings may need a few local before/after probes. Do not invent clicks in omitted footage or turn pasted input into fabricated typing. Use the raw high-resolution source for enlarged text when feasible; do not regenerate the app's content to fake a cleaner shot.

Pronunciation: preserve conventional display text in captions, but give TTS explicit spoken forms for risky terms. Confirm identifier readings with the intended audience; the bundled normalizer defaults 1080P to “幺零八零 P”. The shared minimax-tts normalizer applies this at synthesis. Do not mechanically split ordinary quantities or prices. When the user specifies the reading, it is already authorized; avoid fixed A/B/C approval loops. Regenerate only affected speech, recalibrate its captions/scene length, and reuse the other audio. ASR may normalize both different number pronunciations to the same digits; disclose that limitation and inspect a short phonetic segment when possible rather than claiming a subjective listening result.
