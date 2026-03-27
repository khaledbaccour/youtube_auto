"""
Annotation renderer — red circles, arrows, and highlight overlays.
Hand-drawn wobble effect for authenticity.
"""

import os
import random
from PIL import Image, ImageDraw
from moviepy import ImageClip
import numpy as np

from shorts_config import (
    ANNOTATION_CIRCLE_COLOR, ANNOTATION_CIRCLE_WIDTH,
    WIDTH, HEIGHT,
)


def create_red_circle(center_x, center_y, radius, start_s, end_s, frame_size=None):
    """Create a red circle annotation overlay as a timed ImageClip.

    Coordinates are in pixels. Use create_annotations_from_script() for
    normalized (0-1) coordinates.
    """
    if frame_size is None:
        frame_size = (WIDTH, HEIGHT)

    w, h = frame_size

    # Create transparent RGBA image
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Parse color
    color = ANNOTATION_CIRCLE_COLOR
    if color.startswith("#"):
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
    else:
        r, g, b = 255, 0, 0

    stroke = ANNOTATION_CIRCLE_WIDTH

    # Draw with hand-drawn wobble: draw multiple slightly offset arcs
    num_passes = 3
    for _ in range(num_passes):
        # Wobble offsets for hand-drawn look
        ox = random.randint(-2, 2)
        oy = random.randint(-2, 2)
        rw = random.randint(-3, 3)

        x0 = center_x - radius + ox + rw
        y0 = center_y - radius + oy + rw
        x1 = center_x + radius + ox - rw
        y1 = center_y + radius + oy - rw

        draw.ellipse(
            [x0, y0, x1, y1],
            outline=(r, g, b, 255),
            width=stroke,
        )

    # Convert to numpy array for MoviePy
    arr = np.array(img)

    clip = ImageClip(arr, is_mask=False, transparent=True)
    clip = clip.with_start(start_s)
    clip = clip.with_duration(end_s - start_s)

    return clip


def create_arrow(start_xy, end_xy, start_s, end_s, frame_size=None):
    """Create a red arrow annotation overlay."""
    if frame_size is None:
        frame_size = (WIDTH, HEIGHT)

    w, h = frame_size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    color = ANNOTATION_CIRCLE_COLOR
    if color.startswith("#"):
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
    else:
        r, g, b = 255, 0, 0

    stroke = ANNOTATION_CIRCLE_WIDTH

    sx, sy = start_xy
    ex, ey = end_xy

    # Draw main line
    draw.line([(sx, sy), (ex, ey)], fill=(r, g, b, 255), width=stroke)

    # Draw arrowhead
    import math
    angle = math.atan2(ey - sy, ex - sx)
    arrow_len = 20
    arrow_angle = 0.5  # radians

    ax1 = ex - arrow_len * math.cos(angle - arrow_angle)
    ay1 = ey - arrow_len * math.sin(angle - arrow_angle)
    ax2 = ex - arrow_len * math.cos(angle + arrow_angle)
    ay2 = ey - arrow_len * math.sin(angle + arrow_angle)

    draw.polygon(
        [(ex, ey), (int(ax1), int(ay1)), (int(ax2), int(ay2))],
        fill=(r, g, b, 255),
    )

    arr = np.array(img)
    clip = ImageClip(arr, is_mask=False, transparent=True)
    clip = clip.with_start(start_s)
    clip = clip.with_duration(end_s - start_s)
    return clip


def create_annotations_from_script(segments, frame_size=None):
    """Parse annotation definitions from script segments.

    Coordinates in the script are normalized 0-1. This converts them to pixels.

    Returns: list of timed ImageClip overlays
    """
    if frame_size is None:
        frame_size = (WIDTH, HEIGHT)

    w, h = frame_size
    clips = []

    # Track cumulative time offset per segment
    time_offset = 0.0

    for seg in segments:
        annotations = seg.get("annotations", [])
        seg_duration = seg.get("duration_hint_s", 5.0)

        for ann in annotations:
            ann_type = ann.get("type", "circle")
            # Times are relative to segment start
            a_start = time_offset + ann.get("start_s", 0.0)
            a_end = time_offset + ann.get("end_s", 2.0)

            if ann_type == "circle":
                cx = int(ann.get("x", 0.5) * w)
                cy = int(ann.get("y", 0.5) * h)
                r = int(ann.get("radius", 0.1) * min(w, h))

                clip = create_red_circle(cx, cy, r, a_start, a_end, frame_size)
                clips.append(clip)

            elif ann_type == "arrow":
                sx = int(ann.get("start_x", 0.3) * w)
                sy = int(ann.get("start_y", 0.3) * h)
                ex = int(ann.get("end_x", 0.7) * w)
                ey = int(ann.get("end_y", 0.7) * h)

                clip = create_arrow((sx, sy), (ex, ey), a_start, a_end, frame_size)
                clips.append(clip)

        time_offset += seg_duration

    print(f"  Created {len(clips)} annotation overlays")
    return clips


if __name__ == "__main__":
    # Quick test: red circle on black background
    from moviepy import ColorClip, CompositeVideoClip

    bg = ColorClip(size=(WIDTH, HEIGHT), color=(30, 30, 30)).with_duration(3.0)
    circle = create_red_circle(
        center_x=WIDTH // 2, center_y=HEIGHT // 3,
        radius=150, start_s=0.5, end_s=2.5,
    )

    final = CompositeVideoClip([bg, circle], size=(WIDTH, HEIGHT))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "test_annotation.mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    final.write_videofile(out, fps=30, codec="libx264", preset="fast")
    print(f"  Test annotation: {out}")
