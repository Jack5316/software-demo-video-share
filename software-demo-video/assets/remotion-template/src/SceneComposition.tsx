import React from 'react';
import {AbsoluteFill, Audio, OffthreadVideo, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import scenePlan from './scenePlan.json';
import {FocusMotion,FocusKey,ClickCue} from './FocusMotion';

type SceneProps = {sceneId: string; sceneIndex: number};
type Caption = {start: number; end: number; text: string};
type Mask = {x: number; y: number; width: number; height: number; color: string};
type Scene = {
  id: string;
  title: string;
  audioFile: string;
  videoFile: string;
  durationInFrames: number;
  captions: Caption[];
  overlay: 'none' | 'search' | 'success';
  baseScale: number;
  transformOrigin: string;
  masks: Mask[];
  camera?: FocusKey[];
  clicks?: ClickCue[];
};
const plan = scenePlan as {scenes: Scene[]};
const fontFamily = 'PingFang SC, Hiragino Sans GB, Microsoft YaHei, sans-serif';

export const SceneComposition: React.FC<SceneProps> = ({sceneId, sceneIndex}) => {
  const scene = plan.scenes.find((item) => item.id === sceneId);
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  if (!scene) throw new Error(`Unknown scene: ${sceneId}`);
  const seconds = frame / fps;
  const caption = scene.captions.find((item) => seconds >= item.start && seconds < item.end)?.text ?? '';
  const scale = scene.baseScale;
  const progress = interpolate(frame, [0, durationInFrames - 1], [8, 100], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const successOpacity = interpolate(frame, [30, 60], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{backgroundColor: '#07101f', fontFamily}}>
      <FocusMotion camera={scene.camera} clicks={scene.clicks}>
      <AbsoluteFill>
        <OffthreadVideo src={staticFile(`video/${scene.videoFile}`)} muted style={{width: '100%', height: '100%', objectFit: 'contain', transform: `scale(${scale})`, transformOrigin: scene.transformOrigin}} />
      </AbsoluteFill>
      {scene.masks.map((mask, index) => <div key={index} style={{position: 'absolute', left: mask.x, top: mask.y, width: mask.width, height: mask.height, backgroundColor: mask.color}} />)}
      </FocusMotion>
      <Audio src={staticFile(`audio/${scene.audioFile}`)} />
      <div style={{position: 'absolute', top: 28, left: 38, padding: '11px 19px', borderRadius: 999, background: 'rgba(15,23,42,0.84)', color: 'white', fontSize: 27, fontWeight: 700, boxShadow: '0 8px 28px rgba(15,23,42,0.2)'}}>软件操作演示</div>
      <div style={{position: 'absolute', top: 28, right: 38, padding: '10px 18px', borderRadius: 16, background: 'rgba(255,255,255,0.94)', color: '#0f172a', fontSize: 25, fontWeight: 650, border: '1px solid rgba(15,23,42,0.1)'}}>{sceneIndex + 1}/{plan.scenes.length} · {scene.title}</div>
      {scene.overlay === 'search' ? (
        <div style={{position: 'absolute', left: '50%', top: '43%', transform: 'translate(-50%, -50%)', width: 620, padding: '34px 42px', borderRadius: 28, background: 'rgba(15,23,42,0.91)', color: 'white', boxShadow: '0 24px 90px rgba(15,23,42,0.35)'}}>
          <div style={{display: 'flex', alignItems: 'center', gap: 20}}>
            <div style={{width: 42, height: 42, borderRadius: '50%', border: '5px solid rgba(255,255,255,0.28)', borderTopColor: '#22c55e', transform: `rotate(${frame * 8}deg)`}} />
            <div><div style={{fontSize: 34, fontWeight: 700}}>处理中</div><div style={{fontSize: 23, opacity: 0.76, marginTop: 5}}>已压缩实际等待时间</div></div>
          </div>
          <div style={{height: 8, borderRadius: 999, background: 'rgba(255,255,255,0.18)', marginTop: 24}}><div style={{height: '100%', width: `${progress}%`, borderRadius: 999, background: '#22c55e'}} /></div>
        </div>
      ) : null}
      {scene.overlay === 'success' ? <div style={{position: 'absolute', right: 64, top: 126, padding: '15px 23px', borderRadius: 18, background: 'rgba(22,163,74,0.94)', color: 'white', fontSize: 28, fontWeight: 700, opacity: successOpacity, boxShadow: '0 12px 36px rgba(22,163,74,0.28)'}}>✓ 结果已核对</div> : null}
      {caption ? <div style={{position: 'absolute', left: 70, right: 70, bottom: 34, display: 'flex', justifyContent: 'center'}}><div style={{maxWidth: 1580, padding: '17px 28px 19px', borderRadius: 18, background: 'rgba(8,15,28,0.9)', color: 'white', fontSize: caption.length > 42 ? 34 : 38, lineHeight: 1.42, fontWeight: 560, textAlign: 'center', boxShadow: '0 12px 38px rgba(2,6,23,0.28)'}}>{caption}</div></div> : null}

    </AbsoluteFill>
  );
};
