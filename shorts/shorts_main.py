"""
Shorts pipeline orchestrator — runs the full pipeline end-to-end.
Can be run directly or via agent teams.
"""

import os
import sys
import json
import time

# Ensure shorts/ is on the path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shorts_config import OUTPUT_DIR
from shorts_script_writer import load_shorts_script, validate_shorts_script
from shorts_tts import generate_narration_with_timestamps
from video_sourcer import fetch_clips_for_script
from shorts_assembler import assemble_short


def run_shorts_pipeline(script_path=None):
    """Run the complete Shorts pipeline.

    Steps:
        1. Load and validate script
        2. Generate TTS narration with word timestamps
        3. Fetch and prepare video clips
        4. Assemble final Short (video + audio + captions + annotations)

    Returns: path to final MP4
    """
    start_time = time.time()
    print("=" * 60)
    print("  SHORTS PIPELINE")
    print("=" * 60)

    # Step 1: Load and validate script
    print("\n[1/4] Loading script...")
    script = load_shorts_script(script_path)
    if not script:
        print("  ABORT: No script found")
        return None

    is_valid, issues = validate_shorts_script(script)
    if not is_valid:
        print("  ABORT: Script validation failed")
        return None

    print(f"  Title: {script['title']}")
    print(f"  Segments: {len(script['segments'])}")

    # Step 2: Generate TTS with word timestamps
    print("\n[2/4] Generating narration...")
    narration = script["full_narration"]
    audio_path = os.path.join(OUTPUT_DIR, "audio", "narration.wav")

    duration, word_timestamps = generate_narration_with_timestamps(narration, audio_path)
    if not duration or not word_timestamps:
        print("  ABORT: TTS generation failed")
        return None

    # Save timestamps for debugging
    ts_path = os.path.join(OUTPUT_DIR, "audio", "word_timestamps.json")
    with open(ts_path, "w") as f:
        json.dump(word_timestamps, f, indent=2)
    print(f"  Saved word timestamps: {ts_path}")

    # Step 3: Fetch video clips
    print("\n[3/4] Fetching video clips...")
    clip_paths = fetch_clips_for_script(script)
    if not clip_paths:
        print("  ABORT: No video clips fetched")
        return None

    # Step 4: Assemble
    print("\n[4/4] Assembling Short...")
    output_path = os.path.join(OUTPUT_DIR, "short.mp4")
    result = assemble_short(
        script=script,
        clip_paths=clip_paths,
        audio_path=audio_path,
        word_timestamps=word_timestamps,
        output_path=output_path,
    )

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"  DONE in {elapsed:.0f}s")
    print(f"  Output: {result}")
    print(f"{'=' * 60}")

    return result


if __name__ == "__main__":
    script_file = sys.argv[1] if len(sys.argv) > 1 else None
    run_shorts_pipeline(script_file)
