"""
Caption renderer — word-by-word yellow captions with grow animation.
Each word appears one at a time, starting at 1.0x and growing to ~1.35x.
"""

import os
from moviepy import TextClip, CompositeVideoClip, ColorClip

from shorts_config import (
    CAPTION_FONT, CAPTION_FONT_SIZE, CAPTION_COLOR,
    CAPTION_STROKE_COLOR, CAPTION_STROKE_WIDTH,
    CAPTION_Y_POSITION, CAPTION_SCALE_START, CAPTION_SCALE_END,
    WIDTH, HEIGHT,
)

# Minimum display time for a word (prevents invisible flashes)
MIN_WORD_DURATION = 0.08


def create_word_clips(word_timestamps, frame_w=None, frame_h=None):
    """Create a list of TextClips, one per word, with grow animation.

    Args:
        word_timestamps: [{"word": "Why", "start_s": 0.0, "end_s": 0.07}, ...]
        frame_w: frame width (default 1080)
        frame_h: frame height (default 1920)

    Returns: list of MoviePy TextClip objects with timing and grow effect
    """
    if frame_w is None:
        frame_w = WIDTH
    if frame_h is None:
        frame_h = HEIGHT

    clips = []
    y_pos = int(frame_h * CAPTION_Y_POSITION)

    for ts in word_timestamps:
        word = ts["word"].upper().strip()
        if not word:
            continue

        start = ts["start_s"]
        end = ts["end_s"]
        duration = max(end - start, MIN_WORD_DURATION)

        # Create the text clip
        txt_clip = TextClip(
            text=word,
            font=_find_font(),
            font_size=CAPTION_FONT_SIZE,
            color=CAPTION_COLOR,
            stroke_color=CAPTION_STROKE_COLOR,
            stroke_width=CAPTION_STROKE_WIDTH,
        )

        # Apply grow animation: scale from 1.0x to 1.35x over the word's duration
        scale_range = CAPTION_SCALE_END - CAPTION_SCALE_START

        def make_scale_func(dur, sr=scale_range, ss=CAPTION_SCALE_START):
            def scale_func(t):
                progress = t / dur if dur > 0 else 0
                return ss + sr * progress
            return scale_func

        txt_clip = txt_clip.resized(make_scale_func(duration))

        # Position and time
        txt_clip = txt_clip.with_position(("center", y_pos))
        txt_clip = txt_clip.with_start(start)
        txt_clip = txt_clip.with_duration(duration)

        clips.append(txt_clip)

    print(f"  Created {len(clips)} word caption clips")
    return clips


def _find_font():
    """Find Impact font on the system."""
    candidates = [
        "impact.ttf",
        "Impact.ttf",
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/Impact.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",
        "/System/Library/Fonts/Impact.ttf",
    ]

    for path in candidates:
        if os.path.exists(path):
            return path

    # If impact not found, try the project's Bangers font
    project_font = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets", "fonts", "Bangers-Regular.ttf"
    )
    if os.path.exists(project_font):
        return project_font

    return "impact.ttf"  # let MoviePy try to find it


if __name__ == "__main__":
    # Quick visual test
    test_timestamps = [
        {"word": "Why", "start_s": 0.0, "end_s": 0.4},
        {"word": "are", "start_s": 0.4, "end_s": 0.7},
        {"word": "African", "start_s": 0.7, "end_s": 1.2},
        {"word": "mechanics", "start_s": 1.2, "end_s": 1.9},
        {"word": "so", "start_s": 1.9, "end_s": 2.1},
        {"word": "muscular?", "start_s": 2.1, "end_s": 2.8},
    ]

    word_clips = create_word_clips(test_timestamps)

    # Compose on black background for preview
    bg = ColorClip(size=(WIDTH, HEIGHT), color=(0, 0, 0)).with_duration(3.0)
    final = CompositeVideoClip([bg] + word_clips, size=(WIDTH, HEIGHT))

    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "output", "test_captions.mp4"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    final.write_videofile(out_path, fps=30, codec="libx264", preset="fast")
    print(f"  Test captions video: {out_path}")
