export interface ScenePrompt {
  scene_id: number;
  visual_type: "image" | "video";
  scene_category: string;
  image_prompt: string;
  video_prompt: string;
  style: string;
  duration_s: number;
  script_reference: string;
}

export interface ScenePromptsData {
  total_scenes: number;
  total_duration_s: number;
  character_description: string;
  scenes: ScenePrompt[];
}

export interface ResolvedScene {
  scene_id: number;
  visual_type: "image" | "video";
  src: string;
  duration_s: number;
  durationInFrames: number;
}

export interface BabyVideoProps {
  scenesFile: string;
  scenes?: ResolvedScene[];
}
