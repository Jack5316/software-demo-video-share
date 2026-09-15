# WorkBuddy validation example

This is a reusable test scenario, not proof that every app can be automated.

Use the installed desktop WorkBuddy and inspect the version. Start from a clean new task, collapse private history and account areas. Preserve the user's configured model; use the model chosen by the user. Verify the visible custom-model label, never open/export secret model configuration for the recording.

A small non-sensitive test: ask for three steps to organize a desk, each at most twelve Chinese characters, only answer in chat without file operations or network research. Record entering the request, sending it, and reading the actual completed response. Keep AI waiting separate or explicitly mark it removed. Verify three steps and length against the actual answer before writing the result narration. Do not fabricate a success view or substitute a screenshot.

Use bundle identity discovered locally, not guessed window IDs. On the tested macOS app it is `com.tencent.workbuddy.mac`; still verify it on a new machine. Inspect new panels and dialogs for independent windows and private content. Keep input focus stable while recording.

Acceptance: real UI steps recorded in an isolated-window video, configured clone identity verified, rendered action scenes aligned with speech, full media decode plus sampled transition/pixel review and actual audio content verification (state whether listened to or ASR-only). Record current date/version/model label and all limits in the task report; store no live accounts, machine IDs, absolute user paths, videos or voice IDs in this Skill.

Observed 2026-09-06 on WorkBuddy 5.5.3: background follow-up paste could leave the input unchanged. Re-read AX/pixels; raising the target window with CUA and pasting again restored input. Do not send until the exact request is visible. The first answer added explanations despite a length limit; a follow-up to remove explanations produced the requested three short steps. This is a useful validation path, not a guaranteed response.

## Teacher’s Day case: efficient checks (2026-09-06)

The 249-second tutorial was rendered as 19 scenes. The old rule extracted 140 frames into 47 contact sheets and required external plan/final/incremental reviews; an expired reviewer login blocked a task the owner could execute. Those were workflow costs, not reasons to require the same coverage again.

Useful findings and where to focus next time:

- Model prose called a 1536×1024 image “16:9” and a visibly AI-marked video “without watermark”. Probe actual dimensions/duration and inspect the visible mark; never narrate these claims solely from chat text.
- A PPT page had three broken icon placeholders. Inspect the suspect asset style/its repetitions, replace those icons in the app with native text, then verify the repair. This does not require reviewing every otherwise stable page.
- A video-credit prompt appeared before submission. Existing user authorization covered one generation; confirm that action only, with privacy checks around the prompt. Do not choose persistent permission merely to simplify recording.
- AX included an encoded accountSnapshot URL; tool activity could expose local paths. Omit encoded account URLs from saved AX, keep raw takes private, and inspect menus/path-producing transitions and final masks closely.
- Short source/voice misalignment needed a local clip adjustment; external SRT needed the measured join correction described in action-sync.md. Reuse unchanged audio and pixels.

A suitable risk selection would include model menu exposure, the generation-credit transition, generated-result claims, the repaired icon page, the long-caption/menu layout and a late subtitle join, plus a small baseline. Choose timestamps from the actual final edit; do not copy the old case’s numbers or turn this list into a universal quota.

## Expert group vs Expert (2026-09-07)

「专家团」is **not** the top-bar「专家」tab and **not** a sidebar primary item.

It is the **secondary tab to the right of「专家」**, under「精选场景」, on the「专家·技能·连接器」page. Left =「专家」(individual experts). Right =「专家团」(expert teams).

Failure mode: a vague prompt like “进入专家/专家团（可能是顶栏专家）” makes Codex click「专家」and open an individual card (e.g. 公益专家) while reporting PASS. That is the wrong leaf.

Correct minimal validation: click secondary「专家团」→ open one team detail (e.g. 软件开发团队 / MVP开发专家团). Do **not** click 召唤/召集. Verify with AX that「专家团」is selected / Value 1 and「专家」is Value 0.

User-drawn red boxes on screenshots are post-hoc location hints only — **nothing red exists on the live UI**. Never attach marked screenshots or ask Codex to “find the red box”. Use plain-language position only.

## Usage demo vs minimal validation (2026-09-07 lesson)

Minimal validation (click「专家团」→ open one team detail, do **not** 召唤) remains valid for permission/path checks only.

A **usage / tutorial delivery** is different. A 科研专家团 usage-demo lesson: stopping before 召唤 is unacceptable when they asked to 使用专家团 and record real work. For usage demos you MUST:

1. Open the correct「专家团」secondary tab and a relevant team (e.g. 科研专家团).
2. Actually click 召唤/召集 (or the product equivalent) and start a real collaboration.
3. Provide concrete materials (e.g. a small public GitHub dataset CSV already staged on disk) and a concrete ask (e.g. analyze the data and draft a short paper).
4. Keep recording through attach/paste, send, waiting (mark removed waits), and visible progress or partial results. Narrate only observed outcomes.
5. Edit with **required** `clicks` (mouse highlight) on every meaningful click and **`camera`** focus zoom on click/input/selection — matching the polish of earlier WorkBuddy intro videos. Camera-only detail zooms without click rings failed user expectation.

Acceptance for usage demos: isolated-window footage shows summon + materials + task in flight or completed enough to show the team working; scene plan contains calibrated `clicks` and `camera` for those actions; final MP4 delivered through the user-selected channel.

## Electron process name + Chinese paste (2026-09-10)

WorkBuddy.app is Electron. In **System Events** the process name is **`Electron`**, not `WorkBuddy`. Keystrokes / menu clicks aimed at `process "WorkBuddy"` silently miss; paste appears to “succeed” while the composer stays on stale text and **Send stays disabled**.

### Do
1. Resolve the real pid: `pgrep -f '/Applications/WorkBuddy.app/Contents/MacOS/Electron$'`.
2. `pbcopy` UTF-8 task text, then target that **unix id**: activate WorkBuddy → set that Electron process frontmost → Cmd+A → Delete → menu 编辑/粘贴 (or Cmd+V). A small helper (`wb-paste-zh.sh`) that binds pid + pbcopy is preferred over ad-hoc CUA paste.
3. AX-verify a unique marker from the task (e.g. `6000–8000`) **and** that Send is enabled before clicking Send.
4. Prefer **Finder drag-drop** for attachments; after any file-picker Open, require a visible attachment chip — dialog close alone is not proof.
5. Dirty leftover dialogs / sticky composer text: `quit app "WorkBuddy"` → reopen → re-walk the hard path. Do not keep hammering a polluted session.

### Do not
- `typeText` long Chinese (drops Han characters).
- Rely on AX `setValue` alone (text may show; Send often stays disabled without real input events).
- Keep the authorized Computer Use runtime/session alive until operations finish.

Verify the current app process identity: an input-targeting failure does not establish that the machine cannot record.

## Before a formal take

Confirm Chinese text and Send state, and a visible attachment chip. Keep the operating session alive. If a session is polluted, preserve user work before reopening it. During a long wait, edits may be prepared, but a partial draft is not a finished delivery. Confirm final MP4 and matching captions before handing over the result.
