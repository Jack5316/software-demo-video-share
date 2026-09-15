import React from 'react';
import {Composition} from 'remotion';
import scenePlan from './scenePlan.json';
import {SceneComposition} from './SceneComposition';

type RootScene = {id: string; durationInFrames: number};
const plan = scenePlan as {fps: number; width: number; height: number; audioSampleRate: number; outputFilename: string; scenes: RootScene[]};

export const RemotionRoot: React.FC = () => (
  <>
    {plan.scenes.map((scene, sceneIndex) => (
      <Composition
        key={scene.id}
        id={scene.id}
        component={SceneComposition}
        durationInFrames={scene.durationInFrames}
        fps={plan.fps}
        width={plan.width}
        height={plan.height}
        defaultProps={{sceneId: scene.id, sceneIndex}}
      />
    ))}
  </>
);
