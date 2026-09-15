# Capture modes and recording handshake

## Supported modes

| Mode | Built-in support | User may work concurrently? | Raw privacy scope |
|---|---|---|---|
| Exclusive display | Yes: `screencapture -v -D<N>` | No; pause input during the short active segment | Entire selected display |
| Secondary display | Yes: `-D<N>` after display verification | Mostly; work elsewhere, but avoid stealing operated-app focus | Entire selected secondary display |
| Window-only (default) | `WindowRecorder.swift`, macOS 15+ | Other apps cannot occlude capture; shared input can interfere | Selected window, including its private contents |
| Dedicated Mac/VM/session | External route | Yes | Isolated environment selected by caller |

Do not claim post-production cropping reduces the privacy scope of raw full-display footage.

Persistent classroom OBS profiles are protected. Preview read-only. If a source is offline/black, do not mutate that profile for an unrelated demo. A temporary isolated OBS scene is allowed only after the caller follows applicable configuration-management rules and proves the preview.

## User-availability decision

- **User can pause briefly:** prefer short window segments; use explicitly selected display capture when needed. Full-screen is optional but often stabilizes geometry and excludes menu bar/Dock.
- **User must keep using the Mac:** prefer a verified window capture or isolated environment. Warn that global keyboard/mouse focus can still interfere.
- **True parallel work required:** use a dedicated Mac/VM/session. Do not promise non-interference on one interactive desktop.

## Dry run and coordinate discipline

1. Prefer AX element indices.
2. Use coordinates only when AX cannot represent the target.
3. Record app-screenshot dimensions and coordinate space.
4. Click during rehearsal, verify the exact target, then record the calibrated coordinate; re-calibrate if layout/scale changes.
5. Never mix physical pixels, logical display pixels, and resized screenshot pixels.

## Segment timing

Derive duration from rehearsed active time:

`segment_seconds = max(active_seconds * 2.5 + 3, active_seconds + 8)`

This margin covers tool latency, not unpredictable model generation. Submission and waiting are separate segments.

## Handshake

`record_segment.py` emits newline-delimited JSON:

- `READY`: the direct non-interactive display recorder is alive after backend start delay; UI operation may begin.
- `COMPLETED`: natural exit and duration/stream probe passed.
- `REJECTED`: process failure, interruption, early exit, or invalid artifact.

Accept only `COMPLETED`. Process presence or the macOS orange indicator does not prove clean pixels.

## Take review and retry

Inspect a representative retained result and any risky transitions; do not extract first/middle/last and interval grids by default. Record a short accept/reject reason when a problem or uncertainty warrants it. Retry only the failed segment. After two failed takes, revise the action map/backend or involve the user.

## True window backend

Adapted from obsidian-handdraw-video v1.1.3 (2026-09-06); maintained here as a self-contained generic recorder. No Obsidian runtime dependency.

```bash
xcrun swiftc -parse-as-library "$SKILL_DIR/scripts/WindowRecorder.swift" -o work/WindowRecorder
work/WindowRecorder --output work/probe.mp4 --stop-file work/probe.stop --bundle '<app bundle>' --title '<unique title>' --max-seconds 4
```

Use `--window-id` instead of `--title` only after verifying that ID. A missing/ambiguous match fails; never guess largest window. Inspect probe frames with another app foreground to verify occlusion isolation. The filter is `SCContentFilter(desktopIndependentWindow:)`; separate popups/windows may not be included, so rehearse and inspect these. Never broaden scope silently.

For longer capture use a fresh output/stop path and a bounded `--max-seconds`. Save JSON TARGET/READY/COMPLETED; READY contains UTC and monotonic clocks for action timing. Stop by creating the stop-file in another call. READY is recording-start callback, not proof of later health. Require natural completion and media/frame review; `.partial.mp4` stays private. New permission prompts require user handling. Unsupported OS/permission fails without substituting display mode.
