import React from "react";
import { Composition } from "remotion";
import { BabyVideo } from "./BabyVideo";
import { loadScenes, getTotalDurationInFrames } from "./load-scenes";
import type { ResolvedScene } from "./types";

const FPS = 30;
const WIDTH = 1920;
const HEIGHT = 1080;

// Default fallback: 11 minutes
const DEFAULT_DURATION_FRAMES = 11 * 60 * FPS;

export const Root: React.FC = () => {
  return (
    <>
      <Composition
        id="BabyVideo"
        component={BabyVideo}
        durationInFrames={DEFAULT_DURATION_FRAMES}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={{
          scenes: [] as ResolvedScene[],
        }}
        calculateMetadata={async ({ props }) => {
          // When --props is passed with scene_prompts.json path, load scenes
          const propsAny = props as any;
          let scenes: ResolvedScene[] = [];

          if (propsAny.scenesFile) {
            scenes = loadScenes(propsAny.scenesFile);
          } else if (propsAny.scenes && propsAny.scenes.length > 0) {
            scenes = propsAny.scenes;
          }

          const totalFrames =
            scenes.length > 0
              ? getTotalDurationInFrames(scenes)
              : DEFAULT_DURATION_FRAMES;

          return {
            durationInFrames: totalFrames,
            props: { scenes },
          };
        }}
      />
    </>
  );
};
