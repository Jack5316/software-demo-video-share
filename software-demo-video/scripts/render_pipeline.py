#!/usr/bin/env python3
"""Preview and incrementally render an already materialized software-demo project.

Machine QA is evidence generation, never a substitute for final human/model review.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def key(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def write(path, payload):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def fingerprints(project, plan):
    """Shared code/layout/runtime changes invalidate all; scene media changes only its scene."""
    referenced = {f'public/{kind}/{s[field]}' for s in plan['scenes'] for kind, field in [('audio', 'audioFile'), ('video', 'videoFile')]}
    shared_files = [p for folder in ['src', 'scripts', 'public'] for p in (project / folder).rglob('*')
                    if p.is_file() and p.relative_to(project).as_posix() not in referenced | {'src/scenePlan.json'}]
    shared_files += [p for name in ['package.json', 'package-lock.json', 'tsconfig.json', 'node_modules/remotion/package.json', 'node_modules/@remotion/cli/package.json'] if (p := project / name).exists()]
    shared_files += [p for p in project.glob('remotion.config.*') if p.is_file()]
    ffmpeg = os.environ.get('SOFTWARE_DEMO_FFMPEG') or ('/opt/homebrew/bin/ffmpeg' if Path('/opt/homebrew/bin/ffmpeg').exists() else shutil.which('ffmpeg'))
    ff_version = subprocess.check_output([ffmpeg, '-version'], text=True).splitlines()[0] if ffmpeg else None
    shared = {'encoder_runtime': [ffmpeg, ff_version], 'files': {str(p.relative_to(project)): digest(p) for p in shared_files},
              'pipeline': digest(__file__), 'globals': {k: v for k, v in plan.items() if k != 'scenes'},
              'order': [s['id'] for s in plan['scenes']]}
    return {s['id']: key({'shared': shared, 'scene': s,
                         'audio': digest(project / 'public/audio' / s['audioFile']),
                         'video': digest(project / 'public/video' / s['videoFile'])}) for s in plan['scenes']}


def reusable(receipt, fingerprint, output):
    return bool(receipt and receipt.get('key') == fingerprint and output.is_file()
                and receipt.get('sha256') == digest(output))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--stage', choices=['preview', 'build'], required=True)
    p.add_argument('--scene', help='Preview scene ID; default longest caption scene')
    p.add_argument('--frame', type=int, help='Preview frame; defaults to scene midpoint')
    p.add_argument('--preview-reviewed', action='store_true', help='Caller actually inspected current preview pixels/clip')
    p.add_argument('--samples', type=Path, help='Risk points JSON passed to final QA')
    a = p.parse_args()
    project = a.project.resolve()
    plan_path = project / 'src/scenePlan.json'
    plan = json.loads(plan_path.read_text())
    keys = fingerprints(project, plan)
    out = project / 'out'; out.mkdir(exist_ok=True)
    cache_path = out / 'pipeline-cache.json'
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    cli = str(project / 'node_modules/.bin/remotion')
    def run(command):
        subprocess.run(command, cwd=project, check=True)
    def save():
        write(cache_path, cache)
    if a.stage == 'preview':
        scene = next((s for s in plan['scenes'] if s['id'] == a.scene), None) if a.scene else max(plan['scenes'], key=lambda s: max((len(c['text']) for c in s['captions']), default=0))
        if scene is None:
            p.error('unknown preview scene')
        frame = a.frame if a.frame is not None else scene['durationInFrames'] // 2
        if not 0 <= frame < scene['durationInFrames']:
            p.error('preview frame out of bounds')
        still, clip = out / 'preview.png', out / 'preview.mp4'
        run([cli, 'still', 'src/index.ts', scene['id'], str(still), f'--frame={frame}', '--log=error'])
        start = max(0, frame - plan['fps'])
        end = min(scene['durationInFrames'] - 1, start + plan['fps'] * 3 - 1)
        run([cli, 'render', 'src/index.ts', scene['id'], str(clip), f'--frames={start}-{end}', '--codec=h264', '--log=error', '--concurrency=4'])
        cache['preview'] = {'scene': scene['id'], 'key': keys[scene['id']], 'still_sha256': digest(still), 'clip_sha256': digest(clip)}
        save(); print(json.dumps({'stage': 'preview', 'scene': scene['id'], 'review_required': True})); return
    preview = cache.get('preview', {})
    if not (a.preview_reviewed and preview.get('key') == keys.get(preview.get('scene'))
            and (out / 'preview.png').exists() and (out / 'preview.mp4').exists()
            and preview.get('still_sha256') == digest(out / 'preview.png')
            and preview.get('clip_sha256') == digest(out / 'preview.mp4')):
        p.error('create and inspect a current preview, then use --preview-reviewed')
    (out / 'scenes').mkdir(exist_ok=True)
    rendered, skipped = [], []
    for scene in plan['scenes']:
        sid = scene['id']; output = out / 'scenes' / f'{sid}.mp4'
        if reusable(cache.get('scenes', {}).get(sid), keys[sid], output):
            skipped.append(sid); continue
        run([cli, 'render', 'src/index.ts', sid, str(output), '--codec=h264', '--crf=18', '--log=error', '--concurrency=4'])
        cache.setdefault('scenes', {})[sid] = {'key': keys[sid], 'sha256': digest(output)}
        save(); rendered.append(sid)
    final = out / plan['outputFilename']
    concat_key = key({'scenes': [cache['scenes'][s['id']] for s in plan['scenes']], 'script': digest(project / 'scripts/concat.sh'),
                      'plan': digest(plan_path)})
    concatenated = not reusable(cache.get('concat'), concat_key, final)
    if concatenated:
        run(['bash', 'scripts/concat.sh'])
        cache['concat'] = {'key': concat_key, 'sha256': digest(final)}; save()
    qa_script = Path(__file__).with_name('qa_final.py')
    qa_dir = out / 'qa'
    qa_key = key({'final': digest(final), 'srt': digest(out / 'final.srt'), 'plan': digest(plan_path),
                  'samples': digest(a.samples) if a.samples else None, 'qa': digest(qa_script), 'common': digest(qa_script.with_name('_common.py'))})
    # Always refresh final evidence after a changed artifact. A prior verdict is deliberately not supplied.
    qa_receipt = cache.get('qa', {})
    qa_files = {str(f.relative_to(qa_dir)): digest(f) for f in qa_dir.rglob('*') if f.is_file() and f.name != 'review-verdict.json'} if qa_dir.exists() else {}
    qa_ran = not (qa_receipt.get('key') == qa_key and qa_files and qa_receipt.get('files') == qa_files)
    if qa_ran:
        run([sys.executable, str(qa_script), '--video', str(final), '--srt', str(out / 'final.srt'), '--scene-plan', str(plan_path), '--out-dir', str(qa_dir)] + (['--samples', str(a.samples.resolve())] if a.samples else []))
        cache['qa'] = {'key': qa_key, 'files': {str(f.relative_to(qa_dir)): digest(f) for f in qa_dir.rglob('*') if f.is_file() and f.name != 'review-verdict.json'}}; save()
    print(json.dumps({'rendered': rendered, 'reused': skipped, 'concatenated': concatenated, 'machine_qa_ran': qa_ran,
                      'final': str(final), 'release_review': 'Run qa_final --require-verdict with the owner’s risk-based review before delivery'}))


if __name__ == '__main__':
    main()
