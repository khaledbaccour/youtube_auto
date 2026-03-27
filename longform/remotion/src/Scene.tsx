import React from "react";
import {
  AbsoluteFill,
  Img,
  OffthreadVideo,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  staticFile,
} from "remotion";
import type { ResolvedScene } from "./types";

interface SceneProps {
  scene: ResolvedScene;
}

export const Scene: React.FC<SceneProps> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  // Subtle slow zoom effect (Ken Burns lite) for images
  const scale = interpolate(frame, [0, scene.durationInFrames], [1.0, 1.05], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const containerStyle: React.CSSProperties = {
    width: "100%",
    height: "100%",
    overflow: "hidden",
    backgroundColor: "#FFF5E6", // warm cream fallback
  };

  const mediaStyle: React.CSSProperties = {
    width: "100%",
    height: "100%",
    objectFit: "cover" as const,
    transform: scene.visual_type === "image" ? `scale(${scale})` : undefined,
  };

  return (
    <AbsoluteFill style={containerStyle}>
      {scene.visual_type === "video" ? (
        <OffthreadVideo src={scene.src} style={mediaStyle} />
      ) : (
        <Img src={scene.src} style={mediaStyle} />
      )}
    </AbsoluteFill>
  );
};
