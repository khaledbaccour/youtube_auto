"""Helper functions for the agent-team-driven video pipeline.
Called by Claude Code agents via: python -c "from run_pipeline_agents import X; X()"
"""
import os, json
from datetime import datetime
from config import BASE_DIR, OUTPUT_DIR

VIRALITY_PILLARS = """
## THE 5 VIRALITY PILLARS
1. THE HOOK (First 5s): Open loop, curiosity gap, most surprising fact first. Measured by 30s retention.
2. THE CLICK (Title+Thumbnail): Power words, numbers, curiosity, 40-60 char titles. Measured by CTR.
3. THE RETENTION (Keep Watching): Pattern interrupt every 60-90s, visual variety, pacing. Measured by avg view duration.
4. THE ENGAGEMENT (Comments+Shares): Strong opinions, predictions, controversy. Measured by comments/views ratio.
5. THE ALGORITHM (Session Time): 4-6 min optimal, comment velocity, subs/view ratio. Measured by subscriber gain.
"""

def get_pipeline_context():
    """Step 1: Sync analytics + build context. Returns JSON string."""
    from database import init_db
    from youtube_analytics import sync_all_analytics
    from performance_analyzer import generate_insights
    from feedback_loop import build_pipeline_context, update_claude_md_insights

    init_db()
    try:
        sync_all_analytics()
        generate_insights()
        update_claude_md_insights()
    except Exception as e:
        print(f"Analytics sync failed (non-fatal): {e}")

    context = build_pipeline_context()
    print(json.dumps(context, indent=2, default=str))
    return context

def run_tts():
    """Step 4: Generate TTS from output/script.json. Prints result JSON."""
    from script_writer import load_script
    from tts_engine import generate_continuous_audio

    script_path = os.path.join(OUTPUT_DIR, "script.json")
    title, scenes, full_narration = load_script(script_path)
    audio_path = os.path.join(OUTPUT_DIR, "audio", "full_narration.wav")
    os.makedirs(os.path.dirname(audio_path), exist_ok=True)
    duration = generate_continuous_audio(full_narration, audio_path)

    result = {"title": title, "scene_count": len(scenes),
              "audio_path": audio_path, "duration": duration,
              "narration_length": len(full_narration)}
    print(json.dumps(result))
    return result

def validate_script():
    """Validate output/script.json against CLAUDE.md rules. Prints issues."""
    from script_writer import load_script, validate_script as _validate

    script_path = os.path.join(OUTPUT_DIR, "script.json")
    title, scenes, full_narration = load_script(script_path)
    is_valid, issues = _validate(scenes)
    result = {"valid": is_valid, "issues": issues, "title": title, "scene_count": len(scenes)}
    print(json.dumps(result, indent=2))
    return result

def run_frames_and_assembly():
    """Step 7: Build frames + assemble video. Prints video path."""
    from script_writer import load_script
    from scene_builder import build_scenes
    from video_assembler import assemble_video_continuous
    from tts_engine import calculate_scene_durations, _get_wav_duration

    script_path = os.path.join(OUTPUT_DIR, "script.json")
    title, scenes, full_narration = load_script(script_path)

    audio_path = os.path.join(OUTPUT_DIR, "audio", "full_narration.wav")
    duration = _get_wav_duration(audio_path)

    frame_paths = build_scenes(scenes)
    scene_durations = calculate_scene_durations(scenes, duration)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    video_path = os.path.join(OUTPUT_DIR, f"video_{timestamp}.mp4")
    assemble_video_continuous(frame_paths, scene_durations, audio_path, video_path)

    result = {"video_path": video_path, "frame_count": len(frame_paths),
              "duration": duration, "title": title}
    print(json.dumps(result))
    return result

def run_qa_review():
    """Step 8: Run QA review on generated video. Prints report."""
    from script_writer import load_script
    from qa_reviewer import review_video_quality, review_title_description, generate_qa_report
    from tts_engine import _get_wav_duration
    import glob

    script_path = os.path.join(OUTPUT_DIR, "script.json")
    title, scenes, full_narration = load_script(script_path)

    audio_path = os.path.join(OUTPUT_DIR, "audio", "full_narration.wav")
    duration = _get_wav_duration(audio_path)

    frame_dir = os.path.join(OUTPUT_DIR, "frames")
    frame_paths = sorted(glob.glob(os.path.join(frame_dir, "scene_*.png")))

    script_data = {"title": title, "scenes": scenes, "full_narration": full_narration}
    video_review = review_video_quality(script_data, frame_paths, duration)
    title_review = review_title_description(title, "")
    qa_report = generate_qa_report(video_review, title_review)

    print(qa_report)
    return qa_report

def store_and_email(qa_report=""):
    """Step 9: Store video in DB + send review email."""
    from script_writer import load_script
    from database import init_db, insert_video, update_video_status
    from email_notifier import send_review_email
    import glob

    init_db()
    script_path = os.path.join(OUTPUT_DIR, "script.json")
    title, scenes, full_narration = load_script(script_path)

    # Find latest video
    video_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "video_*.mp4")))
    video_path = video_files[-1] if video_files else os.path.join(OUTPUT_DIR, "video.mp4")
    thumbnail_path = os.path.join(OUTPUT_DIR, "thumbnail.png")

    video_id = insert_video(
        title=title, topic="", topic_category="", script_pattern="",
        hook_style="", video_file_path=video_path,
        thumbnail_path=thumbnail_path if os.path.exists(thumbnail_path) else None,
    )
    update_video_status(video_id, "pending_review")

    send_review_email(
        video_id=video_id, title=title, topic="",
        script_summary=full_narration[:500], qa_report=qa_report,
        thumbnail_path=thumbnail_path if os.path.exists(thumbnail_path) else None,
        video_path=video_path,
    )
    print(f"Video ID: {video_id}, status: pending_review, email sent.")
    return video_id

def get_virality_pillars():
    """Print the 5 Virality Pillars for agent context."""
    print(VIRALITY_PILLARS)
