import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import { Scene } from "./Scene";
import type { ResolvedScene } from "./types";

interface BabyVideoProps {
  scenes: ResolvedScene[];
}

export const BabyVideo: React.FC<BabyVideoProps> = ({ scenes }) => {
  if (!scenes || scenes.length === 0) {
    return (
      <AbsoluteFill
        style={{
          backgroundColor: "#FFF5E6",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "Arial, sans-serif",
          fontSize: 48,
          color: "#4A3728",
        }}
      >
        No scenes loaded. Place images in output/images/
      </AbsoluteFill>
    );
  }

  let cumulativeFrame = 0;

  return (
    <AbsoluteFill style={{ backgroundColor: "#FFF5E6" }}>
      {scenes.map((scene) => {
        const from = cumulativeFrame;
        cumulativeFrame += scene.durationInFrames;

        return (
          <Sequence
            key={scene.scene_id}
            from={from}
            durationInFrames={scene.durationInFrames}
          >
            <Scene scene={scene} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
