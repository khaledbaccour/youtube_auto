"""
Shorts assembler — combines video clips + TTS audio + word captions +
annotations into a final 1080x1920 portrait MP4.
"""

import os
from moviepy import (
    VideoFileClip, AudioFileClip, CompositeVideoClip,
    concatenate_videoclips, ColorClip,
)

from shorts_config import WIDTH, HEIGHT, FPS, OUTPUT_DIR
from caption_renderer import create_word_clips
from annotation_renderer import create_annotations_from_script


def assemble_short(script, clip_paths, audio_path, word_timestamps, output_path=None):
    """Assemble a complete YouTube Short.

    Args:
        script: parsed script dict
        clip_paths: list of prepared video clip paths (one per segment)
        audio_path: path to TTS narration WAV
        word_timestamps: [{"word": "...", "start_s": ..., "end_s": ...}, ...]
        output_path: where to save final MP4

    Returns: output file path
    """
    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, "short.mp4")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    segments = script.get("segments", [])

    # Load audio to get total duration
    audio_clip = AudioFileClip(audio_path)
    total_duration = audio_clip.duration

    # Calculate segment durations from word timestamps
    segment_durations = _calculate_segment_durations(segments, word_timestamps, total_duration)

    print(f"  Total duration: {total_duration:.1f}s across {len(segments)} segments")
    for i, dur in enumerate(segment_durations):
        print(f"    Segment {i+1}: {dur:.1f}s")

    # Build base video from clips
    base_video = _build_base_video(clip_paths, segment_durations, total_duration)

    # Create word-by-word caption clips
    print("  Rendering captions...")
    caption_clips = create_word_clips(word_timestamps, WIDTH, HEIGHT)

    # Create annotation overlays
    print("  Rendering annotations...")
    annotation_clips = create_annotations_from_script(segments, (WIDTH, HEIGHT))

    # Composite all layers: base video + annotations + captions (captions on top)
    print("  Compositing layers...")
    all_layers = [base_video] + annotation_clips + caption_clips
    final = CompositeVideoClip(all_layers, size=(WIDTH, HEIGHT))
    final = final.with_audio(audio_clip)
    final = final.with_duration(total_duration)

    # Export
    print(f"  Exporting {WIDTH}x{HEIGHT} @ {FPS}fps to {output_path}...")
    final.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
    )
    print(f"  Short saved: {output_path}")
    return output_path


def _calculate_segment_durations(segments, word_timestamps, total_duration):
    """Calculate each segment's duration based on word timestamps.

    Maps each segment's narration to its words in the timestamp list
    to determine precise start/end times.
    """
    if not word_timestamps:
        # Fallback: proportional by narration length
        char_counts = [len(s.get("narration", "")) for s in segments]
        total_chars = sum(char_counts) or 1
        return [(c / total_chars) * total_duration for c in char_counts]

    durations = []
    word_idx = 0
    total_words = len(word_timestamps)

    for seg in segments:
        seg_narration = seg.get("narration", "")
        seg_words = seg_narration.split()
        seg_word_count = len(seg_words)

        if seg_word_count == 0 or word_idx >= total_words:
            durations.append(seg.get("duration_hint_s", 3.0))
            continue

        # Find start time of this segment's first word
        seg_start = word_timestamps[word_idx]["start_s"]

        # Advance through the words for this segment
        end_idx = min(word_idx + seg_word_count, total_words) - 1
        seg_end = word_timestamps[end_idx]["end_s"]

        durations.append(seg_end - seg_start)
        word_idx = end_idx + 1

    # Normalize to match total audio duration
    dur_sum = sum(durations) or 1
    scale = total_duration / dur_sum
    durations = [d * scale for d in durations]

    return durations


def _build_base_video(clip_paths, segment_durations, total_duration):
    """Build the base video by concatenating prepared clips."""
    video_clips = []

    for i, (clip_path, duration) in enumerate(zip(clip_paths, segment_durations)):
        try:
            clip = VideoFileClip(clip_path)
            clip = clip.without_audio()

            # Resize to target if needed
            if clip.size != [WIDTH, HEIGHT]:
                clip = clip.resized((WIDTH, HEIGHT))

            # Trim to segment duration
            if clip.duration > duration:
                clip = clip.subclipped(0, duration)
            elif clip.duration < duration:
                # Loop the clip to fill duration
                loops = int(duration / clip.duration) + 1
                from moviepy import concatenate_videoclips as concat
                clip = concat([clip] * loops).subclipped(0, duration)

            clip = clip.with_duration(duration)
            video_clips.append(clip)

        except Exception as e:
            print(f"  WARNING: Failed to load clip {clip_path}: {e}")
            # Fallback: black frame
            black = ColorClip(
                size=(WIDTH, HEIGHT), color=(0, 0, 0)
            ).with_duration(duration)
            video_clips.append(black)

    if not video_clips:
        return ColorClip(size=(WIDTH, HEIGHT), color=(0, 0, 0)).with_duration(total_duration)

    base = concatenate_videoclips(video_clips, method="chain")
    return base


if __name__ == "__main__":
    print("Use shorts_main.py to run the full pipeline")
