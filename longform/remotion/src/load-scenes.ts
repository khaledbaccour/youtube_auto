import path from "path";
import fs from "fs";
import type { ScenePromptsData, ResolvedScene } from "./types";

const FPS = 30;

export function loadScenes(scenesFilePath: string): ResolvedScene[] {
  const absolutePath = path.isAbsolute(scenesFilePath)
    ? scenesFilePath
    : path.resolve(__dirname, "..", scenesFilePath);

  const raw = fs.readFileSync(absolutePath, "utf-8");
  const data: ScenePromptsData = JSON.parse(raw);

  const outputDir = path.resolve(__dirname, "..", "..", "output");
  const imagesDir = path.join(outputDir, "images");
  const videosDir = path.join(outputDir, "videos");

  return data.scenes.map((scene) => {
    const padded = `scene_${String(scene.scene_id).padStart(3, "0")}`;
    let src: string;

    if (scene.visual_type === "video") {
      src = path.join(videosDir, `${padded}.mp4`);
    } else {
      src = path.join(imagesDir, `${padded}.png`);
    }

    return {
      scene_id: scene.scene_id,
      visual_type: scene.visual_type,
      src,
      duration_s: scene.duration_s,
      durationInFrames: Math.round(scene.duration_s * FPS),
    };
  });
}

export function getTotalDurationInFrames(scenes: ResolvedScene[]): number {
  return scenes.reduce((sum, s) => sum + s.durationInFrames, 0);
}
