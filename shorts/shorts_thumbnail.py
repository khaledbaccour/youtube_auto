"""
Shorts thumbnail generator — creates 1280x720 YouTube thumbnails.
Adapts the root thumbnail_generator.py for Shorts-specific needs,
using a hero frame extracted from video clips.
"""

import os
import sys
import json

# Add parent dir for imports from main pipeline
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw
from scene_builder import (
    TITLE_FONT_PATH,
    TEXT_COLOR,
    ACCENT_RED,
    _load_font,
    _wrap_text,
    _strip_accent_markers,
    _text_shadow,
    _text_stroke,
    _render_rich_text,
    _fit_image,
    _round_corners,
)
from shorts_config import OUTPUT_DIR
from shorts_research import extract_hero_frame

THUMB_W, THUMB_H = 1280, 720


def _render_hero_right(img, draw, headline, hero_img, font, accent_color):
    """Hero image on right, headline text on left."""
    if hero_img:
        hero = _fit_image(hero_img, 540, 540)
        hero = _round_corners(hero, radius=20)
        img.paste(hero.convert("RGB"), (700, 90), hero.split()[3])
    _render_headline(draw, headline, font, 60, THUMB_H // 2, 600, "left", accent_color)


def _render_hero_left(img, draw, headline, hero_img, font, accent_color):
    """Hero image on left, headline text on right."""
    if hero_img:
        hero = _fit_image(hero_img, 540, 540)
        hero = _round_corners(hero, radius=20)
        img.paste(hero.convert("RGB"), (40, 90), hero.split()[3])
    _render_headline(draw, headline, font, 620, THUMB_H // 2, 620, "left", accent_color)


def _render_center_dramatic(img, draw, headline, hero_img, font, accent_color):
    """Full-bleed hero darkened with centered text."""
    if hero_img:
        bg = _fit_image(hero_img, THUMB_W, THUMB_H)
        overlay = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 160))
        bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
        img.paste(bg, (0, 0))

    big_font = _load_font(TITLE_FONT_PATH, 140)
    lines = _wrap_text(draw, headline, big_font, THUMB_W - 160)
    while len(lines) > 2 and big_font.size > 80:
        big_font = _load_font(TITLE_FONT_PATH, big_font.size - 10)
        lines = _wrap_text(draw, headline, big_font, THUMB_W - 160)

    line_height = big_font.size + 28
    total_h = len(lines) * line_height
    start_y = (THUMB_H - total_h) // 2

    for line in lines:
        clean = _strip_accent_markers(line)
        bbox = draw.textbbox((0, 0), clean, font=big_font)
        lx = (THUMB_W - (bbox[2] - bbox[0])) // 2
        if "*" in line:
            parts = line.split("*")
            cx = lx
            for j, part in enumerate(parts):
                if not part:
                    continue
                color = accent_color if j % 2 == 1 else TEXT_COLOR
                _text_stroke(draw, (cx, start_y), part, big_font, color, stroke_width=5)
                bbox = draw.textbbox((0, 0), part, font=big_font)
                cx += bbox[2] - bbox[0]
        else:
            _text_stroke(draw, (lx, start_y), line, big_font, TEXT_COLOR, stroke_width=5)
        start_y += line_height


def _render_headline(draw, text, font, x, y, max_w, align, accent_color):
    """Render headline with accent word support."""
    lines = _wrap_text(draw, text, font, max_w)
    line_height = font.size + 24
    total_h = len(lines) * line_height
    start_y = y - total_h // 2

    for line in lines:
        if align == "center":
            clean = _strip_accent_markers(line)
            bbox = draw.textbbox((0, 0), clean, font=font)
            lx = x + (max_w - (bbox[2] - bbox[0])) // 2
        else:
            lx = x

        if "*" in line:
            _render_rich_text(draw, (lx, start_y), line, font, TEXT_COLOR, offset=5, accent_color=accent_color)
        else:
            _text_shadow(draw, (lx, start_y), line, font, TEXT_COLOR, offset=5)
        start_y += line_height


LAYOUTS = {
    "hero_right": _render_hero_right,
    "hero_left": _render_hero_left,
    "center_dramatic": _render_center_dramatic,
}


def generate_shorts_thumbnail(script, output_path=None):
    """Generate a 1280x720 thumbnail for a YouTube Short.

    Args:
        script: Parsed script dict with 'thumbnail' and 'title' fields.
        output_path: Where to save the PNG.

    Returns:
        Path to saved thumbnail.
    """
    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, "thumbnail.png")
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    thumb = script.get("thumbnail", {})
    layout = thumb.get("layout", "hero_right")
    headline = thumb.get("headline") or script.get("title", "")[:40]
    accent_color = thumb.get("accent_color", ACCENT_RED)

    # Try to extract hero frame from first prepared clip
    hero_img = None
    clips_dir = os.path.join(OUTPUT_DIR, "clips")
    if os.path.exists(clips_dir):
        prepared = sorted([
            os.path.join(clips_dir, f) for f in os.listdir(clips_dir)
            if f.endswith("_prepared.mp4")
        ])
        if prepared:
            hero_path = os.path.join(OUTPUT_DIR, "hero_frame.jpg")
            if extract_hero_frame(prepared[0], 2.0, hero_path):
                try:
                    hero_img = Image.open(hero_path).convert("RGB")
                except Exception:
                    pass

    # Create canvas
    img = Image.new("RGB", (THUMB_W, THUMB_H), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _load_font(TITLE_FONT_PATH, 120)

    # Render
    renderer = LAYOUTS.get(layout, _render_hero_right)
    if not hero_img and layout in ("hero_right", "hero_left"):
        renderer = _render_center_dramatic
    renderer(img, draw, headline, hero_img, font, accent_color)

    img.save(output_path, "PNG")
    print(f"Shorts thumbnail saved: {output_path} ({THUMB_W}x{THUMB_H})")
    return output_path


if __name__ == "__main__":
    script_path = os.path.join(OUTPUT_DIR, "script.json")
    if os.path.exists(script_path):
        with open(script_path) as f:
            script = json.load(f)
        generate_shorts_thumbnail(script)
    else:
        print(f"No script at {script_path}")
