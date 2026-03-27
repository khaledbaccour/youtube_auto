"""
Agent-callable entry points for the Shorts pipeline.
Each function can be invoked independently by Claude Code agents:
    python -c "from shorts.run_shorts_agents import run_shorts_tts; run_shorts_tts()"
"""

import os
import sys
import json

# Ensure shorts/ is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shorts_config import OUTPUT_DIR


def run_shorts_tts():
    """Generate TTS audio + word timestamps from script narration."""
    from shorts_script_writer import load_shorts_script
    from shorts_tts import generate_narration_with_timestamps

    script = load_shorts_script()
    if not script:
        print(json.dumps({"success": False, "error": "No script found"}))
        return

    narration = script["full_narration"]
    audio_path = os.path.join(OUTPUT_DIR, "audio", "narration.wav")

    duration, timestamps = generate_narration_with_timestamps(narration, audio_path)

    if not duration:
        print(json.dumps({"success": False, "error": "TTS failed"}))
        return

    # Save timestamps
    ts_path = os.path.join(OUTPUT_DIR, "audio", "word_timestamps.json")
    with open(ts_path, "w") as f:
        json.dump(timestamps, f, indent=2)

    print(json.dumps({
        "success": True,
        "audio_path": audio_path,
        "duration_s": round(duration, 2),
        "word_count": len(timestamps),
        "timestamps_path": ts_path,
    }))


def run_shorts_clips():
    """Fetch and prepare video clips from the script source."""
    from shorts_script_writer import load_shorts_script
    from video_sourcer import fetch_clips_for_script

    script = load_shorts_script()
    if not script:
        print(json.dumps({"success": False, "error": "No script found"}))
        return

    clip_paths = fetch_clips_for_script(script)

    print(json.dumps({
        "success": bool(clip_paths),
        "clip_count": len(clip_paths),
        "clip_paths": clip_paths,
    }))


def run_shorts_assembly():
    """Assemble final Short from pre-generated audio and clips."""
    from shorts_script_writer import load_shorts_script
    from shorts_assembler import assemble_short

    script = load_shorts_script()
    if not script:
        print(json.dumps({"success": False, "error": "No script found"}))
        return

    # Load pre-generated timestamps
    ts_path = os.path.join(OUTPUT_DIR, "audio", "word_timestamps.json")
    if not os.path.exists(ts_path):
        print(json.dumps({"success": False, "error": "No word timestamps — run TTS first"}))
        return

    with open(ts_path, "r") as f:
        word_timestamps = json.load(f)

    audio_path = os.path.join(OUTPUT_DIR, "audio", "narration.wav")
    if not os.path.exists(audio_path):
        print(json.dumps({"success": False, "error": "No audio — run TTS first"}))
        return

    # Find prepared clips
    clips_dir = os.path.join(OUTPUT_DIR, "clips")
    clip_paths = sorted([
        os.path.join(clips_dir, f)
        for f in os.listdir(clips_dir)
        if f.startswith("segment_") and f.endswith("_prepared.mp4")
    ]) if os.path.exists(clips_dir) else []

    if not clip_paths:
        print(json.dumps({"success": False, "error": "No clips — run clip fetcher first"}))
        return

    output_path = os.path.join(OUTPUT_DIR, "short.mp4")
    result = assemble_short(script, clip_paths, audio_path, word_timestamps, output_path)

    print(json.dumps({
        "success": bool(result),
        "output_path": result,
    }))


def validate_shorts_script_cmd():
    """Validate the current script against rules."""
    from shorts_script_writer import load_shorts_script, validate_shorts_script

    script = load_shorts_script()
    if not script:
        print(json.dumps({"success": False, "error": "No script found"}))
        return

    is_valid, issues = validate_shorts_script(script)
    print(json.dumps({
        "success": is_valid,
        "issues": issues,
        "title": script.get("title"),
        "word_count": len(script.get("full_narration", "").split()),
        "segment_count": len(script.get("segments", [])),
    }))


def run_video_search(query=None):
    """Search YouTube for viral AI money-making videos."""
    from shorts_research import search_youtube_videos
    from shorts_config import NICHE_TOPICS

    if not query:
        query = NICHE_TOPICS[0]

    candidates = search_youtube_videos(query, max_results=5)

    result = {
        "search_queries_used": [query],
        "candidates": candidates,
        "iteration": 1,
    }

    out_path = os.path.join(OUTPUT_DIR, "video_candidates.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(json.dumps({
        "success": bool(candidates),
        "candidate_count": len(candidates),
        "output_path": out_path,
    }))


def run_video_download_and_cut():
    """Download approved video and cut into clips based on scene analysis."""
    from shorts_research import analyze_video_segments
    from video_sourcer import download_youtube_video, extract_segment, prepare_clip

    approved_path = os.path.join(OUTPUT_DIR, "approved_video.json")
    if not os.path.exists(approved_path):
        print(json.dumps({"success": False, "error": "No approved_video.json"}))
        return

    with open(approved_path) as f:
        approved = json.load(f)

    url = approved["url"]
    clips_dir = os.path.join(OUTPUT_DIR, "clips")
    sources_dir = os.path.join(clips_dir, "sources")
    os.makedirs(sources_dir, exist_ok=True)

    # Download
    video_path = download_youtube_video(url, sources_dir)
    if not video_path:
        print(json.dumps({"success": False, "error": "Download failed"}))
        return

    # Analyze for high-energy segments
    segments = analyze_video_segments(video_path, target_duration=45)
    if not segments:
        print(json.dumps({"success": False, "error": "No segments found"}))
        return

    # Extract and prepare each segment
    manifest_segments = []
    for i, (start, end, score) in enumerate(segments[:8]):
        seg_id = i + 1
        raw_path = os.path.join(clips_dir, f"segment_{seg_id}.mp4")
        prep_path = os.path.join(clips_dir, f"segment_{seg_id}_prepared.mp4")

        extract_segment(video_path, start, end, raw_path)
        prepare_clip(raw_path, end - start, prep_path)

        manifest_segments.append({
            "segment_id": seg_id,
            "video_start_s": round(start, 1),
            "video_end_s": round(end, 1),
            "duration_hint_s": round(end - start, 1),
            "clip_path": prep_path,
            "description": f"Segment {seg_id} (activity score: {score})",
        })

    manifest = {
        "source_video_path": video_path,
        "source_url": url,
        "segments": manifest_segments,
        "total_short_duration_s": round(sum(s["duration_hint_s"] for s in manifest_segments), 1),
    }

    manifest_path = os.path.join(OUTPUT_DIR, "clip_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(json.dumps({
        "success": True,
        "segment_count": len(manifest_segments),
        "total_duration_s": manifest["total_short_duration_s"],
        "manifest_path": manifest_path,
    }))


def run_thumbnail_generation():
    """Generate thumbnail from script and video clips."""
    from shorts_thumbnail import generate_shorts_thumbnail
    from shorts_script_writer import load_shorts_script

    script = load_shorts_script()
    if not script:
        print(json.dumps({"success": False, "error": "No script found"}))
        return

    out_path = os.path.join(OUTPUT_DIR, "thumbnail.png")
    result = generate_shorts_thumbnail(script, out_path)

    print(json.dumps({
        "success": bool(result),
        "thumbnail_path": result,
    }))


def get_shorts_pipeline_context():
    """Return current pipeline state for agents to understand what's done."""
    state = {
        "script_exists": os.path.exists(os.path.join(OUTPUT_DIR, "script.json")),
        "audio_exists": os.path.exists(os.path.join(OUTPUT_DIR, "audio", "narration.wav")),
        "timestamps_exist": os.path.exists(os.path.join(OUTPUT_DIR, "audio", "word_timestamps.json")),
        "short_exists": os.path.exists(os.path.join(OUTPUT_DIR, "short.mp4")),
        "candidates_exist": os.path.exists(os.path.join(OUTPUT_DIR, "video_candidates.json")),
        "approved_exist": os.path.exists(os.path.join(OUTPUT_DIR, "approved_video.json")),
        "manifest_exist": os.path.exists(os.path.join(OUTPUT_DIR, "clip_manifest.json")),
        "thumbnail_exists": os.path.exists(os.path.join(OUTPUT_DIR, "thumbnail.png")),
    }

    # Count clips
    clips_dir = os.path.join(OUTPUT_DIR, "clips")
    if os.path.exists(clips_dir):
        clips = [f for f in os.listdir(clips_dir) if f.endswith("_prepared.mp4")]
        state["clip_count"] = len(clips)
    else:
        state["clip_count"] = 0

    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        funcs = {
            "tts": run_shorts_tts,
            "clips": run_shorts_clips,
            "assembly": run_shorts_assembly,
            "validate": validate_shorts_script_cmd,
            "context": get_shorts_pipeline_context,
            "search": run_video_search,
            "download": run_video_download_and_cut,
            "thumbnail": run_thumbnail_generation,
        }
        if cmd in funcs:
            funcs[cmd]()
        else:
            print(f"Unknown command: {cmd}. Options: {', '.join(funcs.keys())}")
    else:
        print("Usage: python run_shorts_agents.py [tts|clips|assembly|validate|context|search|download|thumbnail]")
