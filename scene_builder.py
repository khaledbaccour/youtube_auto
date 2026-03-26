"""
Fireship-style visual frame composer — generates 1920x1080 dark-themed frames.
Downloads real images from the web for rich visuals.
"""

import os
import re
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from image_fetcher import fetch_image

# --- Constants ---
WIDTH, HEIGHT = 1920, 1080
BG_COLOR = "#000000"
TEXT_COLOR = "#F5F5DC"
ACCENT_PINK = "#FF6B9D"
ACCENT_ORANGE = "#FF8C42"
ACCENT_GREEN = "#4ADE80"

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
TITLE_FONT_PATH = os.path.join(FONT_DIR, "Bangers-Regular.ttf")
BODY_FONT_PATH = os.path.join(FONT_DIR, "Roboto-Bold.ttf")

IMAGE_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "images")

# Stock photo domains that serve watermarked images — skip these
WATERMARK_DOMAINS = [
    "alamy.com", "shutterstock.com", "gettyimages.com", "istockphoto.com",
    "dreamstime.com", "123rf.com", "depositphotos.com", "stockphoto.com",
    "bigstockphoto.com", "adobestock.com", "stock.adobe.com", "photoshelter.com",
    "dissolve.com", "canstockphoto.com", "pond5.com", "vectorstock.com",
    "supermeme.ai", "imgflip.com", "memegenerator.net", "makeameme.org",
    "vecteezy.com", "pokde.net", "freepik.com", "pngtree.com",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _strip_accent_markers(text):
    """Remove *asterisks* for width measurement but keep the words."""
    return re.sub(r'\*([^*]+)\*', r'\1', text)


def _wrap_text(draw, text, font, max_width):
    """Wrap text to fit within max_width pixels. Returns list of lines."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        # Measure without accent markers
        measure_text = _strip_accent_markers(test)
        bbox = draw.textbbox((0, 0), measure_text, font=font)
        if bbox[2] - bbox[0] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines


ACCENT_RED = "#FF3333"


def _text_shadow(draw, xy, text, font, fill, shadow_color="#000000", offset=3):
    """Draw text with a drop shadow for readability."""
    sx, sy = xy
    # Double shadow for stronger effect
    draw.text((sx + offset + 1, sy + offset + 1), text, fill=shadow_color, font=font)
    draw.text((sx + offset, sy + offset), text, fill=shadow_color, font=font)
    draw.text((sx, sy), text, fill=fill, font=font)


def _text_stroke(draw, xy, text, font, fill, stroke_color="#000000", stroke_width=3):
    """Draw text with a thick stroke/outline for emphasis (Fireship style)."""
    sx, sy = xy
    # Draw stroke at offsets around the text
    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx * dx + dy * dy <= stroke_width * stroke_width:
                draw.text((sx + dx, sy + dy), text, fill=stroke_color, font=font)
    draw.text((sx, sy), text, fill=fill, font=font)


def _render_rich_text(draw, xy, text, font, default_fill, shadow_color="#000000", offset=3):
    """Render text with *red accent* words. Words in *asterisks* render in red with dark stroke."""
    sx, sy = xy
    parts = re.split(r'(\*[^*]+\*)', text)
    cursor_x = sx
    for part in parts:
        if part.startswith('*') and part.endswith('*'):
            word = part[1:-1]
            _text_stroke(draw, (cursor_x, sy), word, font, ACCENT_RED, stroke_color=shadow_color, stroke_width=3)
            bbox = draw.textbbox((0, 0), word, font=font)
            cursor_x += bbox[2] - bbox[0] + 8
        else:
            _text_shadow(draw, (cursor_x, sy), part, font, default_fill, shadow_color, offset)
            bbox = draw.textbbox((0, 0), part, font=font)
            cursor_x += bbox[2] - bbox[0]


def _create_dark_bg():
    """Create a pure black background — Fireship style."""
    return Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))



def _fit_image(img, target_w, target_h):
    """Resize and crop image to fill target dimensions without stretching."""
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    # Center crop
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _round_corners(img, radius=20):
    """Apply rounded corners to an image."""
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, img.size[0], img.size[1]], radius=radius, fill=255)
    img.putalpha(mask)
    return img


# --- Frame Type Renderers ---

def _render_text_only(img, draw, scene):
    """Dark bg, one large bold white text centered. Fireship 'YESTERDAY...' style."""
    text = scene.get("main_text", "")
    if not text:
        return

    font_size = 96
    font = _load_font(TITLE_FONT_PATH, font_size)
    max_w = WIDTH - 300

    lines = _wrap_text(draw, text, font, max_w)
    # Reduce font if too many lines
    while len(lines) > 3 and font_size > 48:
        font_size -= 8
        font = _load_font(TITLE_FONT_PATH, font_size)
        lines = _wrap_text(draw, text, font, max_w)

    line_height = font_size + 20
    total_h = len(lines) * line_height
    start_y = (HEIGHT - total_h) // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (WIDTH - text_w) // 2
        _text_shadow(draw, (x, start_y), line, font, TEXT_COLOR)
        start_y += line_height


def _render_image_with_text(img, draw, scene):
    """Dark bg. Image on right (60%), bold text on left."""
    text = scene.get("main_text", "")
    query = scene.get("image_search_query", "")

    img_path = fetch_image(query) if query else None

    if img_path:
        try:
            photo = Image.open(img_path).convert("RGB")
            target_w = int(WIDTH * 0.55)
            target_h = HEIGHT - 120
            photo = _fit_image(photo, target_w, target_h)
            photo_rounded = _round_corners(photo, radius=16)
            # Place on right side
            paste_x = WIDTH - target_w - 60
            paste_y = 60
            img.paste(photo_rounded.convert("RGB"), (paste_x, paste_y), photo_rounded.split()[3])
        except Exception:
            img_path = None

    # Text on left side
    if text:
        font_size = 64
        font = _load_font(TITLE_FONT_PATH, font_size)
        left_area_w = int(WIDTH * 0.38)
        lines = _wrap_text(draw, text, font, left_area_w)

        while len(lines) > 5 and font_size > 36:
            font_size -= 4
            font = _load_font(TITLE_FONT_PATH, font_size)
            lines = _wrap_text(draw, text, font, left_area_w)

        line_height = font_size + 16
        total_h = len(lines) * line_height
        start_y = (HEIGHT - total_h) // 2
        x = 80

        for line in lines:
            if '*' in line:
                _render_rich_text(draw, (x, start_y), line, font, TEXT_COLOR)
            else:
                _text_shadow(draw, (x, start_y), line, font, TEXT_COLOR)
            start_y += line_height

    if not img_path:
        # Fallback: just render as text_only
        if not text:
            return
        # Already drew the text on left, draw accent bar
        draw.rectangle([60, 200, 68, HEIGHT - 200], fill=ACCENT_PINK)


def _render_article_screenshot(img, draw, scene):
    """Dark bg. Web image centered with padding and border."""
    query = scene.get("image_search_query", "")
    text = scene.get("main_text", "")

    img_path = fetch_image(query) if query else None

    if img_path:
        try:
            photo = Image.open(img_path).convert("RGB")
            target_w = int(WIDTH * 0.75)
            target_h = int(HEIGHT * 0.70)
            photo = _fit_image(photo, target_w, target_h)
            photo_rounded = _round_corners(photo, radius=20)

            # Center it
            paste_x = (WIDTH - target_w) // 2
            paste_y = (HEIGHT - target_h) // 2 - 20

            # Draw a subtle border/glow behind the image
            border = 3
            draw.rounded_rectangle(
                [paste_x - border, paste_y - border,
                 paste_x + target_w + border, paste_y + target_h + border],
                radius=22, outline="#333355", width=border
            )
            img.paste(photo_rounded.convert("RGB"), (paste_x, paste_y), photo_rounded.split()[3])

            # Optional caption at bottom
            if text:
                font = _load_font(BODY_FONT_PATH, 36)
                lines = _wrap_text(draw, text, font, WIDTH - 200)
                y = paste_y + target_h + 20
                for line in lines[:2]:
                    bbox = draw.textbbox((0, 0), line, font=font)
                    tw = bbox[2] - bbox[0]
                    _text_shadow(draw, ((WIDTH - tw) // 2, y), line, font, TEXT_COLOR)
                    y += 48
            return
        except Exception:
            pass

    # Fallback to text_only style
    _render_text_only(img, draw, scene)


def _render_image_grid(img, draw, scene):
    """Side-by-side layout: 2 images (left + right) with bold labels. Clean, not AI-grid."""
    query = scene.get("image_search_query", "")
    labels = scene.get("image_labels", [])
    per_item_queries = scene.get("image_search_queries", [])

    # Use first 2 items only — side by side
    pad = 20
    cell_w = (WIDTH - pad * 3) // 2
    cell_h = HEIGHT - pad * 2

    positions = [
        (pad, pad),
        (pad * 2 + cell_w, pad),
    ]

    label_font = _load_font(TITLE_FONT_PATH, 56)

    for i, (px, py) in enumerate(positions):
        label = labels[i] if i < len(labels) else ""
        if i < len(per_item_queries) and per_item_queries[i]:
            search = per_item_queries[i]
        else:
            search = f"{query} {label}".strip() if query or label else ""

        img_path = fetch_image(search) if search else None

        if img_path:
            try:
                photo = Image.open(img_path).convert("RGB")
                photo = _fit_image(photo, cell_w, cell_h)
                # Darken bottom for label
                overlay = Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))
                ov_draw = ImageDraw.Draw(overlay)
                for j in range(120):
                    alpha = int(j * 2.1)
                    y = cell_h - 120 + j
                    ov_draw.line([(0, y), (cell_w, y)], fill=(0, 0, 0, alpha))
                photo_rgba = photo.convert("RGBA")
                photo_rgba = Image.alpha_composite(photo_rgba, overlay)
                photo_rounded = _round_corners(photo_rgba, radius=16)
                img.paste(photo_rounded.convert("RGB"), (px, py), photo_rounded.split()[3])
            except Exception:
                draw.rectangle([px, py, px + cell_w, py + cell_h], fill="#252545")
        else:
            draw.rectangle([px, py, px + cell_w, py + cell_h], fill="#252545")

        if label:
            bbox = draw.textbbox((0, 0), label, font=label_font)
            tw = bbox[2] - bbox[0]
            lx = px + (cell_w - tw) // 2
            ly = py + cell_h - 80
            _text_shadow(draw, (lx, ly), label, label_font, TEXT_COLOR, offset=4)


def _render_fullscreen_image(img, draw, scene):
    """Image fills ~90% of frame. Thin dark border. Optional text overlay."""
    query = scene.get("image_search_query", "")
    text = scene.get("main_text", "")

    border = 40
    target_w = WIDTH - border * 2
    target_h = HEIGHT - border * 2

    img_path = fetch_image(query) if query else None

    if img_path:
        try:
            photo = Image.open(img_path).convert("RGB")
            photo = _fit_image(photo, target_w, target_h)

            # Darken bottom strip for text overlay
            if text:
                photo_rgba = photo.convert("RGBA")
                overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
                ov_draw = ImageDraw.Draw(overlay)
                for j in range(150):
                    alpha = int(j * 1.7)
                    y = target_h - 150 + j
                    ov_draw.line([(0, y), (target_w, y)], fill=(0, 0, 0, alpha))
                photo = Image.alpha_composite(photo_rgba, overlay).convert("RGB")

            img.paste(photo, (border, border))
        except Exception:
            img_path = None

    if not img_path:
        _render_text_only(img, draw, scene)
        return

    # Text overlay at bottom
    if text:
        font = _load_font(TITLE_FONT_PATH, 52)
        lines = _wrap_text(draw, text, font, WIDTH - 200)
        y = HEIGHT - border - 30 - len(lines) * 64
        for line in lines[:2]:
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            _text_shadow(draw, ((WIDTH - tw) // 2, y), line, font, TEXT_COLOR, offset=4)
            y += 64


def _render_text_bold(img, draw, scene):
    """Large impact text on black — 120px+. For emphasis moments like 'I HAVE A QUESTION...'"""
    text = scene.get("main_text", "")
    if not text:
        return

    font_size = 120
    font = _load_font(TITLE_FONT_PATH, font_size)
    max_w = WIDTH - 300

    lines = _wrap_text(draw, text, font, max_w)
    while len(lines) > 3 and font_size > 64:
        font_size -= 8
        font = _load_font(TITLE_FONT_PATH, font_size)
        lines = _wrap_text(draw, text, font, max_w)

    line_height = font_size + 24
    total_h = len(lines) * line_height
    start_y = (HEIGHT - total_h) // 2

    for line in lines:
        clean = _strip_accent_markers(line)
        bbox = draw.textbbox((0, 0), clean, font=font)
        text_w = bbox[2] - bbox[0]
        x = (WIDTH - text_w) // 2
        if '*' in line:
            _render_rich_text(draw, (x, start_y), line, font, TEXT_COLOR, offset=4)
        else:
            _text_shadow(draw, (x, start_y), line, font, TEXT_COLOR, offset=4)
        start_y += line_height


def _render_meme_fullscreen(img, draw, scene):
    """Fullscreen meme image — for humor beats. No photo filter on search."""
    query = scene.get("image_search_query", "")
    text = scene.get("main_text", "")

    border = 40
    target_w = WIDTH - border * 2
    target_h = HEIGHT - border * 2

    img_path = fetch_image(query, is_meme=True) if query else None

    if img_path:
        try:
            photo = Image.open(img_path).convert("RGB")
            photo = _fit_image(photo, target_w, target_h)

            if text:
                photo_rgba = photo.convert("RGBA")
                overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
                ov_draw = ImageDraw.Draw(overlay)
                for j in range(150):
                    alpha = int(j * 1.7)
                    y = target_h - 150 + j
                    ov_draw.line([(0, y), (target_w, y)], fill=(0, 0, 0, alpha))
                photo = Image.alpha_composite(photo_rgba, overlay).convert("RGB")

            img.paste(photo, (border, border))
        except Exception:
            img_path = None

    if not img_path:
        _render_text_bold(img, draw, scene)
        return

    if text:
        font = _load_font(TITLE_FONT_PATH, 52)
        lines = _wrap_text(draw, text, font, WIDTH - 200)
        y = HEIGHT - border - 30 - len(lines) * 64
        for line in lines[:2]:
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            _text_shadow(draw, ((WIDTH - tw) // 2, y), line, font, TEXT_COLOR, offset=4)
            y += 64



def _render_image_collage(img, draw, scene):
    """2-5 images in organic asymmetric layout with labels."""
    queries = scene.get("image_search_queries", [])
    labels = scene.get("image_labels", [])
    text = scene.get("main_text", "")

    if not queries:
        _render_text_bold(img, draw, scene)
        return

    n = len(queries)
    pad = 20

    # Define cell layouts based on image count
    if n == 2:
        cells = [
            (pad, pad, WIDTH // 2 - pad, HEIGHT - pad),
            (WIDTH // 2 + pad, pad, WIDTH - pad, HEIGHT - pad),
        ]
    elif n == 3:
        mid_x = int(WIDTH * 0.55)
        cells = [
            (pad, pad, mid_x - pad, HEIGHT - pad),
            (mid_x + pad, pad, WIDTH - pad, HEIGHT // 2 - pad),
            (mid_x + pad, HEIGHT // 2 + pad, WIDTH - pad, HEIGHT - pad),
        ]
    elif n == 4:
        cells = [
            (pad, pad, WIDTH // 2 - pad, HEIGHT // 2 - pad),
            (WIDTH // 2 + pad, pad, WIDTH - pad, HEIGHT // 2 - pad),
            (pad, HEIGHT // 2 + pad, WIDTH // 2 - pad, HEIGHT - pad),
            (WIDTH // 2 + pad, HEIGHT // 2 + pad, WIDTH - pad, HEIGHT - pad),
        ]
    else:  # 5+
        cx, cy = WIDTH // 2, HEIGHT // 2
        hw, hh = 550, 350
        cells = [
            (cx - hw, cy - hh, cx + hw, cy + hh),  # center hero
            (pad, pad, cx - hw - pad, cy - pad),  # top-left
            (cx + hw + pad, pad, WIDTH - pad, cy - pad),  # top-right
            (pad, cy + pad, cx - hw - pad, HEIGHT - pad),  # bottom-left
            (cx + hw + pad, cy + pad, WIDTH - pad, HEIGHT - pad),  # bottom-right
        ]

    label_font = _load_font(TITLE_FONT_PATH, 42)

    for i, (x1, y1, x2, y2) in enumerate(cells[:n]):
        cell_w = x2 - x1
        cell_h = y2 - y1
        query = queries[i] if i < len(queries) else ""
        label = labels[i] if i < len(labels) else ""

        img_path = fetch_image(query) if query else None

        if img_path:
            try:
                photo = Image.open(img_path).convert("RGB")
                photo = _fit_image(photo, cell_w, cell_h)
                # Darken bottom for label
                if label:
                    photo_rgba = photo.convert("RGBA")
                    overlay = Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))
                    ov_draw = ImageDraw.Draw(overlay)
                    for j in range(80):
                        alpha = int(j * 3)
                        y = cell_h - 80 + j
                        ov_draw.line([(0, y), (cell_w, y)], fill=(0, 0, 0, alpha))
                    photo = Image.alpha_composite(photo_rgba, overlay).convert("RGB")
                img.paste(photo, (x1, y1))
            except Exception:
                draw.rectangle([x1, y1, x2, y2], fill="#252545")
        else:
            draw.rectangle([x1, y1, x2, y2], fill="#252545")

        if label:
            bbox = draw.textbbox((0, 0), label, font=label_font)
            tw = bbox[2] - bbox[0]
            lx = x1 + (cell_w - tw) // 2
            ly = y2 - 60
            _text_shadow(draw, (lx, ly), label, label_font, TEXT_COLOR, offset=3)


# --- Dispatcher ---

FRAME_RENDERERS = {
    "text_only": _render_text_bold,  # merged into text_bold
    "text_bold": _render_text_bold,
    "image_with_text": _render_image_with_text,
    "article_screenshot": _render_article_screenshot,
    "image_grid": _render_image_grid,
    "fullscreen_image": _render_fullscreen_image,
    "meme_fullscreen": _render_meme_fullscreen,
    "image_collage": _render_image_collage,
}


def _build_single_frame(scene):
    """Build a single 1920x1080 Fireship-style frame. Returns PIL Image."""
    img = _create_dark_bg()
    draw = ImageDraw.Draw(img)

    visual_type = scene.get("visual_type", "text_only")
    renderer = FRAME_RENDERERS.get(visual_type, _render_text_only)
    renderer(img, draw, scene)

    return img


def build_scenes(scenes, output_dir="output/frames", palette_name=None):
    """Build Fireship-style frames for all scenes. Returns list of frame paths.

    Args:
        scenes: List of scene dicts with visual_type, main_text,
                image_search_query, image_labels.
        output_dir: Directory to save frame PNGs.
        palette_name: Kept for API compatibility (unused in dark theme).

    Returns:
        List of output frame file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)
    frame_paths = []

    for i, scene in enumerate(scenes):
        scene_num = str(i + 1).zfill(3)
        frame_path = os.path.join(output_dir, f"scene_{scene_num}.png")
        img = _build_single_frame(scene)
        img.save(frame_path, "PNG")
        frame_paths.append(frame_path)
        vtype = scene.get("visual_type", "text_only")
        print(f"  Frame {scene_num}: {vtype} -> {frame_path}")

    print(f"Generated {len(frame_paths)} frames in {output_dir}")
    return frame_paths


if __name__ == "__main__":
    sample_scenes = [
        {
            "visual_type": "text_only",
            "main_text": "OpenAI just satisfies NO ONE",
        },
        {
            "visual_type": "image_with_text",
            "main_text": "Google releases Gemini 3.0 with native video",
            "image_search_query": "Google Gemini AI logo",
        },
        {
            "visual_type": "article_screenshot",
            "main_text": "The Verge breaks the story first",
            "image_search_query": "AI news article screenshot 2026",
        },
        {
            "visual_type": "image_grid",
            "main_text": "The Big Four of AI",
            "image_search_query": "AI company logo",
            "image_labels": ["OpenAI", "Google", "Anthropic", "Meta"],
        },
        {
            "visual_type": "fullscreen_image",
            "main_text": "The future is already here",
            "image_search_query": "futuristic AI robot concept",
        },
    ]

    paths = build_scenes(sample_scenes, output_dir="output/frames")
    print(f"\nGenerated {len(paths)} sample frames.")
