"""Thumbnail generator — creates 1280x720 YouTube thumbnails in Fireship style."""

import os
from PIL import Image, ImageDraw
from image_fetcher import fetch_image
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

THUMB_W, THUMB_H = 1280, 720


def _render_headline(draw, text, font, x, y, max_w, align, accent_color):
    """Render headline text with accent support. Returns total height used."""
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

    return total_h


def _render_hero_right(img, draw, headline, hero_img, accent_color):
    """Hero image on right, headline text on left."""
    font = _load_font(TITLE_FONT_PATH, 120)

    if hero_img:
        hero = _fit_image(hero_img, 540, 540)
        hero = _round_corners(hero, radius=20)
        img.paste(hero.convert("RGB"), (700, 90), hero.split()[3])

    _render_headline(draw, headline, font, 60, THUMB_H // 2, 600, "left", accent_color)


def _render_hero_left(img, draw, headline, hero_img, accent_color):
    """Hero image on left, headline text on right."""
    font = _load_font(TITLE_FONT_PATH, 120)

    if hero_img:
        hero = _fit_image(hero_img, 540, 540)
        hero = _round_corners(hero, radius=20)
        img.paste(hero.convert("RGB"), (40, 90), hero.split()[3])

    _render_headline(draw, headline, font, 620, THUMB_H // 2, 620, "left", accent_color)


def _render_center_dramatic(img, draw, headline, hero_img, accent_color):
    """Full-bleed hero image with darkened overlay and centered text."""
    if hero_img:
        bg = _fit_image(hero_img, THUMB_W, THUMB_H)
        # Dark overlay
        overlay = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 160))
        bg_rgba = bg.convert("RGBA")
        bg = Image.alpha_composite(bg_rgba, overlay).convert("RGB")
        img.paste(bg, (0, 0))

    font = _load_font(TITLE_FONT_PATH, 140)
    lines = _wrap_text(draw, headline, font, THUMB_W - 160)

    # Reduce font if too many lines
    while len(lines) > 2 and font.size > 80:
        font = _load_font(TITLE_FONT_PATH, font.size - 10)
        lines = _wrap_text(draw, headline, font, THUMB_W - 160)

    line_height = font.size + 28
    total_h = len(lines) * line_height
    start_y = (THUMB_H - total_h) // 2

    for line in lines:
        clean = _strip_accent_markers(line)
        bbox = draw.textbbox((0, 0), clean, font=font)
        tw = bbox[2] - bbox[0]
        lx = (THUMB_W - tw) // 2

        if "*" in line:
            # Use stroke for readability over image
            parts_raw = line.split("*")
            cx = lx
            for j, part in enumerate(parts_raw):
                if not part:
                    continue
                if j % 2 == 1:  # accent word
                    _text_stroke(draw, (cx, start_y), part, font, accent_color, stroke_width=5)
                else:
                    _text_stroke(draw, (cx, start_y), part, font, TEXT_COLOR, stroke_width=5)
                bbox = draw.textbbox((0, 0), part, font=font)
                cx += bbox[2] - bbox[0]
        else:
            _text_stroke(draw, (lx, start_y), line, font, TEXT_COLOR, stroke_width=5)
        start_y += line_height


LAYOUT_RENDERERS = {
    "hero_right": _render_hero_right,
    "hero_left": _render_hero_left,
    "center_dramatic": _render_center_dramatic,
}


def generate_thumbnail(thumbnail_data, title, output_path="output/thumbnail.png"):
    """Generate a 1280x720 YouTube thumbnail.

    Args:
        thumbnail_data: Dict with layout, headline, image_search_query, accent_color.
        title: Video title (fallback headline).
        output_path: Where to save the PNG.

    Returns:
        Path to the saved thumbnail.
    """
    layout = thumbnail_data.get("layout", "hero_right")
    headline = thumbnail_data.get("headline") or title[:40]
    image_query = thumbnail_data.get("image_search_query", "")
    accent_color = thumbnail_data.get("accent_color", ACCENT_RED)

    # Fetch hero image
    hero_img = None
    if image_query:
        img_path = fetch_image(image_query)
        if img_path:
            try:
                hero_img = Image.open(img_path).convert("RGB")
            except Exception:
                pass

    # Create canvas
    img = Image.new("RGB", (THUMB_W, THUMB_H), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Render chosen layout
    renderer = LAYOUT_RENDERERS.get(layout, _render_hero_right)

    # If no hero image for side layouts, fall back to center_dramatic
    if not hero_img and layout in ("hero_right", "hero_left"):
        renderer = _render_center_dramatic

    renderer(img, draw, headline, hero_img, accent_color)

    # Save
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.save(output_path, "PNG")
    print(f"Thumbnail saved: {output_path} ({THUMB_W}x{THUMB_H})")
    return output_path
