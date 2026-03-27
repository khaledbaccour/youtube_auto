"""
Agent-callable entry points for the Longform baby niche pipeline.
Each function can be invoked independently by Claude Code agents:
    python -c "import sys; sys.path.insert(0, 'longform'); from run_longform_agents import validate_script; validate_script()"
"""

import os
import sys
import json
import re

# Ensure longform/ is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from longform_config import OUTPUT_DIR, TARGET_WORD_COUNT_MIN, TARGET_WORD_COUNT_MAX, SCENE_TYPES

# --- Banned phrase list (matches CLAUDE.md) ---
BANNED_PHRASES = [
    "delve", "delving", "dive into", "deep dive", "unpack", "let's unpack",
    "rapidly evolving landscape", "ever-evolving landscape", "fast-paced world",
    "game-changer", "game-changing", "revolutionize", "revolutionary",
    "realm", "tapestry", "testament", "nuance", "nuanced",
    "paradigm", "paradigm shift", "leverage", "utilize", "facilitate",
    "foster", "synergy", "holistic", "robust", "seamless", "seamlessly",
    "cutting-edge", "groundbreaking", "transformative", "pivotal",
    "multifaceted", "comprehensive", "it's important to note",
    "it's worth mentioning", "at the end of the day", "moving forward",
    "in terms of", "when it comes to", "navigate", "embark on a journey",
    "shed light on", "pave the way",
    # Baby niche bans
    "bundle of joy", "little ones", "miracle of life", "precious moments",
    "journey of parenthood", "every parent knows", "as a parent myself",
    "the bond between parent and child", "nurturing environment",
    "developmental milestones", "tiny humans", "kiddos", "munchkins",
    "growing and thriving", "each child is unique",
]


def validate_script():
    """Validate output/script.json against baby niche rules. Prints issues JSON."""
    script_path = os.path.join(OUTPUT_DIR, "script.json")
    if not os.path.exists(script_path):
        print(json.dumps({"success": False, "error": "No script.json found"}))
        return

    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)

    issues = []
    narration = script.get("full_narration", "")
    scenes = script.get("scenes", [])
    title = script.get("title", "")
    word_count = len(narration.split())

    # Word count check
    if word_count < TARGET_WORD_COUNT_MIN:
        issues.append(f"Too short: {word_count} words (need {TARGET_WORD_COUNT_MIN}-{TARGET_WORD_COUNT_MAX})")
    elif word_count > TARGET_WORD_COUNT_MAX + 200:
        issues.append(f"Too long: {word_count} words (target {TARGET_WORD_COUNT_MIN}-{TARGET_WORD_COUNT_MAX})")

    # Banned phrase check
    narration_lower = narration.lower()
    for phrase in BANNED_PHRASES:
        if phrase.lower() in narration_lower:
            issues.append(f"Banned phrase found: '{phrase}'")

    # Sentence length check
    sentences = re.split(r'[.!?]+', narration)
    for i, sentence in enumerate(sentences):
        words_in_sentence = len(sentence.strip().split())
        if words_in_sentence > 25:
            preview = sentence.strip()[:60]
            issues.append(f"Sentence too long ({words_in_sentence} words): '{preview}...'")

    # Contraction check (spot-check common non-contracted forms)
    non_contracted = ["it is ", "they are ", "will not ", "can not ", "does not ", "do not ", "is not ", "are not "]
    for phrase in non_contracted:
        if phrase in narration_lower:
            issues.append(f"Use contraction instead of '{phrase.strip()}'")

    # Scene count check (target: 60 scenes matching reference video)
    if len(scenes) < 50:
        issues.append(f"Too few scenes: {len(scenes)} (target ~60 matching reference video)")
    elif len(scenes) > 70:
        issues.append(f"Too many scenes: {len(scenes)} (target ~60 matching reference video)")

    # Visual type check
    valid_types = {"fullscreen_image", "image_scene", "video_scene"}
    for scene in scenes:
        vt = scene.get("visual_type", "")
        if vt not in valid_types:
            issues.append(f"Scene {scene.get('scene_id')}: invalid visual_type '{vt}'")

    # Check scene narrations are substrings of full_narration
    for scene in scenes:
        scene_narr = scene.get("narration", "")
        if scene_narr and scene_narr not in narration:
            issues.append(f"Scene {scene.get('scene_id')}: narration is not a substring of full_narration")

    # Check consecutive scene type variety (via description, since visual_type is coarse)
    for i in range(1, len(scenes)):
        if scenes[i].get("visual_type") == scenes[i-1].get("visual_type") == "fullscreen_image":
            # This is fine — the variety comes from scene_category in prompts
            pass

    # Title length check
    if len(title) > 100:
        issues.append(f"Title too long: {len(title)} chars (max 100)")
    if not title:
        issues.append("Missing title")

    # full_narration exists
    if not narration:
        issues.append("Missing full_narration")

    is_valid = len(issues) == 0
    result = {
        "success": is_valid,
        "issues": issues,
        "title": title,
        "word_count": word_count,
        "scene_count": len(scenes),
    }
    print(json.dumps(result, indent=2))
    return result


def validate_scene_prompts():
    """Validate output/scene_prompts.json for cartoon style consistency. Prints issues JSON."""
    prompts_path = os.path.join(OUTPUT_DIR, "scene_prompts.json")
    if not os.path.exists(prompts_path):
        print(json.dumps({"success": False, "error": "No scene_prompts.json found"}))
        return

    with open(prompts_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    issues = []
    scenes = data.get("scenes", [])

    for scene in scenes:
        sid = scene.get("scene_id", "?")
        img_prompt = scene.get("image_prompt", "").lower()
        vid_prompt = scene.get("video_prompt", "").lower()
        style = scene.get("style", "").lower()
        category = scene.get("scene_category", "")

        # Must include cartoon style keywords
        cartoon_keywords = ["cartoon", "illustration", "pastel"]
        has_cartoon = any(kw in img_prompt or kw in style for kw in cartoon_keywords)
        if not has_cartoon:
            issues.append(f"Scene {sid}: image_prompt missing cartoon/illustration style keywords")

        # Must not be photorealistic
        bad_keywords = ["photorealistic", "photograph", "stock photo", "dark theme", "black background", "neon"]
        for bk in bad_keywords:
            if bk in img_prompt or bk in vid_prompt:
                issues.append(f"Scene {sid}: contains banned style keyword '{bk}'")

        # Must have valid scene_category
        if category and category not in SCENE_TYPES:
            issues.append(f"Scene {sid}: invalid scene_category '{category}'")

        # Duration check
        duration = scene.get("duration_s", 0)
        if duration < 3:
            issues.append(f"Scene {sid}: duration too short ({duration}s)")
        elif duration > 30:
            issues.append(f"Scene {sid}: duration too long ({duration}s)")

    # Check no two consecutive scenes have same category
    for i in range(1, len(scenes)):
        cat_prev = scenes[i-1].get("scene_category", "")
        cat_curr = scenes[i].get("scene_category", "")
        if cat_prev and cat_curr and cat_prev == cat_curr:
            issues.append(f"Scenes {scenes[i-1].get('scene_id')}-{scenes[i].get('scene_id')}: consecutive same category '{cat_curr}'")

    # Total duration check
    total_dur = sum(s.get("duration_s", 0) for s in scenes)
    if total_dur < 600:
        issues.append(f"Total duration too short: {total_dur}s (need ~660s)")
    elif total_dur > 720:
        issues.append(f"Total duration too long: {total_dur}s (target ~660s)")

    is_valid = len(issues) == 0
    result = {
        "success": is_valid,
        "issues": issues,
        "scene_count": len(scenes),
        "total_duration_s": total_dur,
    }
    print(json.dumps(result, indent=2))
    return result


def check_assets_ready():
    """Check if user has placed images/videos in output dirs. Prints status JSON."""
    prompts_path = os.path.join(OUTPUT_DIR, "scene_prompts.json")
    if not os.path.exists(prompts_path):
        print(json.dumps({"success": False, "error": "No scene_prompts.json — run scene planner first"}))
        return

    with open(prompts_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    scenes = data.get("scenes", [])
    images_dir = os.path.join(OUTPUT_DIR, "images")
    videos_dir = os.path.join(OUTPUT_DIR, "videos")

    missing = []
    found = []

    for scene in scenes:
        sid = scene["scene_id"]
        vtype = scene.get("visual_type", "image")
        padded = f"scene_{sid:03d}"

        if vtype == "video":
            path = os.path.join(videos_dir, f"{padded}.mp4")
        else:
            path = os.path.join(images_dir, f"{padded}.png")

        if os.path.exists(path):
            found.append(padded)
        else:
            missing.append({"scene_id": sid, "expected": path, "type": vtype})

    ready = len(missing) == 0
    result = {
        "success": ready,
        "total_scenes": len(scenes),
        "found": len(found),
        "missing_count": len(missing),
        "missing": missing[:20],  # Show first 20 to avoid huge output
    }
    print(json.dumps(result, indent=2))
    return result


def render_remotion():
    """Trigger Remotion render to assemble final video. Prints result JSON."""
    import subprocess

    remotion_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "remotion")
    scene_data = os.path.join(OUTPUT_DIR, "scene_prompts.json")
    output_video = os.path.join(OUTPUT_DIR, "video.mp4")

    if not os.path.exists(scene_data):
        print(json.dumps({"success": False, "error": "No scene_prompts.json found"}))
        return

    # Check node_modules exists
    if not os.path.exists(os.path.join(remotion_dir, "node_modules")):
        print(json.dumps({"success": False, "error": "Run 'npm install' in longform/remotion/ first"}))
        return

    cmd = [
        "npx", "remotion", "render",
        "src/index.ts", "BabyVideo",
        output_video,
        "--props", scene_data,
    ]

    result = subprocess.run(
        cmd, cwd=remotion_dir,
        capture_output=True, text=True, timeout=600,
    )

    if result.returncode == 0:
        file_size = os.path.getsize(output_video) if os.path.exists(output_video) else 0
        print(json.dumps({
            "success": True,
            "output_path": output_video,
            "file_size_mb": round(file_size / (1024 * 1024), 1),
        }))
    else:
        print(json.dumps({
            "success": False,
            "error": result.stderr[-500:] if result.stderr else "Unknown error",
            "stdout": result.stdout[-500:] if result.stdout else "",
        }))


def get_longform_pipeline_context():
    """Return current pipeline state — which files exist, what's done. Prints JSON."""
    state = {
        "topic_candidates_exist": os.path.exists(os.path.join(OUTPUT_DIR, "topic_candidates.json")),
        "topic_exist": os.path.exists(os.path.join(OUTPUT_DIR, "topic.json")),
        "script_exist": os.path.exists(os.path.join(OUTPUT_DIR, "script.json")),
        "scene_prompts_exist": os.path.exists(os.path.join(OUTPUT_DIR, "scene_prompts.json")),
        "metadata_exist": os.path.exists(os.path.join(OUTPUT_DIR, "metadata.json")),
        "video_exist": os.path.exists(os.path.join(OUTPUT_DIR, "video.mp4")),
    }

    # Count placed assets
    images_dir = os.path.join(OUTPUT_DIR, "images")
    videos_dir = os.path.join(OUTPUT_DIR, "videos")
    state["image_count"] = len([f for f in os.listdir(images_dir) if f.endswith(".png")]) if os.path.exists(images_dir) else 0
    state["video_count"] = len([f for f in os.listdir(videos_dir) if f.endswith(".mp4")]) if os.path.exists(videos_dir) else 0

    print(json.dumps(state, indent=2))
    return state


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        funcs = {
            "validate": validate_script,
            "validate-scenes": validate_scene_prompts,
            "check-assets": check_assets_ready,
            "render": render_remotion,
            "context": get_longform_pipeline_context,
        }
        if cmd in funcs:
            funcs[cmd]()
        else:
            print(f"Unknown command: {cmd}. Options: {', '.join(funcs.keys())}")
    else:
        print("Usage: python run_longform_agents.py [validate|validate-scenes|check-assets|render|context]")
