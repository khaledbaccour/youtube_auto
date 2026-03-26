import os
import sys
import json
import traceback
from datetime import datetime

from config import BASE_DIR, OUTPUT_DIR
from database import init_db, insert_video, update_video_status, get_video
from news_fetcher import get_trending_ai_topic
from script_writer import load_script, validate_script
from tts_engine import generate_continuous_audio, calculate_scene_durations
from image_fetcher import fetch_and_verify_all
from scene_builder import build_scenes
from video_assembler import assemble_video_continuous
from feedback_loop import build_pipeline_context, update_claude_md_insights
from performance_analyzer import generate_insights
from youtube_analytics import sync_all_analytics
from email_notifier import send_review_email, send_error_alert
from qa_reviewer import review_video_quality, review_title_description, generate_qa_report


def run_pipeline():
    """Full pipeline: analytics → context → topic → script → TTS → images → frames → video → QA → email"""
    init_db()

    # Step 1: Analyze past performance (non-fatal)
    print("[1/10] Syncing analytics and generating insights...")
    try:
        sync_all_analytics()
        generate_insights()
        update_claude_md_insights()
    except Exception as e:
        print(f"  Analytics sync failed (non-fatal): {e}")

    # Step 2: Build performance context
    print("[2/10] Building pipeline context...")
    try:
        context = build_pipeline_context()
        print(f"  Best hook: {context.get('best_hook_style', 'N/A')}")
        print(f"  A/B test: {context.get('ab_test', {}).get('variable', 'N/A')}")
    except Exception as e:
        context = {}
        print(f"  Context build failed (non-fatal): {e}")

    # Step 3: Fetch trending topic
    print("[3/10] Fetching trending topic...")
    topic_info = get_trending_ai_topic()
    topic_path = os.path.join(OUTPUT_DIR, "topic.json")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(topic_path, "w") as f:
        json.dump(topic_info, f, indent=2, default=str)
    print(f"  Topic: {topic_info.get('topic', 'Unknown')}")

    # Step 4: Load script (generated externally by Sonnet agent)
    print("[4/10] Loading video script...")
    script_path = os.path.join(OUTPUT_DIR, "script.json")
    if not os.path.exists(script_path):
        print(f"  ERROR: No script at {script_path}. Generate one first.")
        sys.exit(1)

    title, scenes, full_narration = load_script(script_path)
    is_valid, issues = validate_script(scenes)
    print(f"  Title: {title}")
    print(f"  Scenes: {len(scenes)}")
    if not is_valid:
        print("  Validation issues:")
        for issue in issues:
            print(f"    - {issue}")

    # Step 5: Generate TTS audio
    print("[5/10] Generating narration audio...")
    audio_dir = os.path.join(OUTPUT_DIR, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    audio_path = os.path.join(audio_dir, "full_narration.wav")
    total_duration = generate_continuous_audio(full_narration, audio_path)
    print(f"  Audio: {total_duration:.1f}s")

    # Step 6: Fetch and verify images
    print("[6/10] Fetching and verifying images...")
    image_map = fetch_and_verify_all(scenes)
    verified = sum(1 for v in image_map.values() if v)
    print(f"  Images verified: {verified}/{len(image_map)}")

    # Step 7: Build visual frames
    print("[7/10] Building visual frames...")
    frame_paths = build_scenes(scenes)
    print(f"  Frames: {len(frame_paths)}")

    # Step 8: Assemble video
    print("[8/10] Assembling video...")
    scene_durations = calculate_scene_durations(scenes, total_duration)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    video_path = os.path.join(OUTPUT_DIR, f"video_{timestamp}.mp4")
    assemble_video_continuous(frame_paths, scene_durations, audio_path, video_path)
    print(f"  Video: {video_path}")

    # Step 9: QA Review
    print("[9/10] Running QA review...")
    script_data = {"title": title, "scenes": scenes, "full_narration": full_narration}
    video_review = review_video_quality(script_data, frame_paths, total_duration)
    title_review = review_title_description(title, "")
    qa_report = generate_qa_report(video_review, title_review)
    print(f"  Grade: {video_review['overall_grade']} (Virality: {video_review['virality_prediction']}/100)")
    if video_review["issues"]:
        for issue in video_review["issues"]:
            print(f"    - {issue}")

    # Step 10: Store in DB + send review email
    print("[10/10] Storing and sending review email...")
    thumbnail_path = os.path.join(OUTPUT_DIR, "thumbnail.png")
    video_id = insert_video(
        title=title,
        topic=topic_info.get("topic", ""),
        topic_category=context.get("ab_test", {}).get("variable", ""),
        script_pattern=context.get("best_script_pattern", ""),
        hook_style=context.get("best_hook_style", ""),
        video_file_path=video_path,
        description="",
        tags=json.dumps([]),
        thumbnail_path=thumbnail_path if os.path.exists(thumbnail_path) else None,
    )
    update_video_status(video_id, "pending_review")

    send_review_email(
        video_id=video_id,
        title=title,
        topic=topic_info.get("topic", ""),
        script_summary=full_narration[:500],
        qa_report=qa_report,
        thumbnail_path=thumbnail_path if os.path.exists(thumbnail_path) else None,
        video_path=video_path,
    )

    print(f"\nDone! Video ID: {video_id} (status: pending_review)")
    print(f"Video: {video_path}")
    print(f"Grade: {video_review['overall_grade']}")
    return video_id


if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception as e:
        print(f"\nPIPELINE ERROR: {e}")
        traceback.print_exc()
        try:
            send_error_alert(type(e).__name__, str(e), traceback.format_exc())
        except:
            pass
        sys.exit(1)
