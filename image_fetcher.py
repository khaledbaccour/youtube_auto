"""
Standalone image fetcher with download, caching, and verification.
Extracted from scene_builder.py for reuse and enhanced QA.
"""

import os
import re
import hashlib
import requests
import numpy as np
from PIL import Image

# --- Constants ---

IMAGE_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "images")

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


def _search_bing_images(search_query, photo_filter=True):
    """Search Bing Images and return list of image URLs (skipping watermark domains).

    Args:
        search_query: The search string.
        photo_filter: If True, apply photo-photo + large-image filter.

    Returns:
        List of image URL strings.
    """
    search_url = "https://www.bing.com/images/search"
    qft = "+filterui:photo-photo+filterui:imagesize-large" if photo_filter else ""
    params = {"q": search_query, "first": "1", "count": "10"}
    if qft:
        params["qft"] = qft

    resp = requests.get(search_url, params=params, headers=HEADERS, timeout=10)
    resp.raise_for_status()

    img_urls = re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;', resp.text)
    if not img_urls:
        img_urls = re.findall(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp|gif))"', resp.text)

    # Filter out watermark domains
    return [u for u in img_urls[:8] if not any(d in u.lower() for d in WATERMARK_DOMAINS)]


def fetch_image(search_query, is_meme=False):
    """Download an image from Bing Image Search for the given query.

    Uses cache by MD5 hash. Skips watermark domains. For memes, skips the
    photo filter and accepts smaller images.

    Args:
        search_query: The image search string.
        is_meme: If True, skip photo filter and use relaxed size checks.

    Returns:
        Local file path string, or None if download failed.
    """
    if not search_query:
        return None

    os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)

    query_hash = hashlib.md5(search_query.encode()).hexdigest()[:12]
    output_path = os.path.join(IMAGE_CACHE_DIR, f"{query_hash}.jpg")

    # Return cached if exists
    if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        return output_path

    min_w, min_h = (600, 400) if is_meme else (800, 600)
    min_bytes = 15000 if is_meme else 20000

    # First pass: with appropriate filters
    try:
        img_urls = _search_bing_images(search_query, photo_filter=(not is_meme))

        for img_url in img_urls:
            try:
                img_resp = requests.get(img_url, headers=HEADERS, timeout=10, stream=True)
                if img_resp.status_code != 200 or len(img_resp.content) < min_bytes:
                    continue
                with open(output_path, "wb") as f:
                    f.write(img_resp.content)

                test = Image.open(output_path)
                w, h = test.size
                test.verify()
                if w < min_w or h < min_h:
                    continue

                # For memes: reject mostly-white images
                if is_meme:
                    img_check = Image.open(output_path).convert("RGB")
                    pixels = img_check.resize((100, 100)).getdata()
                    white_count = sum(1 for r, g, b in pixels if r > 240 and g > 240 and b > 240)
                    if white_count / len(pixels) > 0.55:
                        continue

                # Save source URL metadata for verification
                meta_path = output_path + ".meta"
                with open(meta_path, "w") as f:
                    f.write(img_url)

                return output_path
            except Exception:
                continue

    except Exception as e:
        print(f"  Image download failed for '{search_query}': {e}")

    # Fallback pass: relax filters (no photo filter, smaller size OK)
    if not is_meme:
        try:
            img_urls = _search_bing_images(search_query, photo_filter=False)
            for img_url in img_urls:
                try:
                    img_resp = requests.get(img_url, headers=HEADERS, timeout=10, stream=True)
                    if img_resp.status_code != 200 or len(img_resp.content) < 5000:
                        continue
                    with open(output_path, "wb") as f:
                        f.write(img_resp.content)
                    test = Image.open(output_path)
                    test.verify()

                    meta_path = output_path + ".meta"
                    with open(meta_path, "w") as f:
                        f.write(img_url)

                    return output_path
                except Exception:
                    continue
        except Exception:
            pass

    return None


def verify_image(image_path, is_meme=False):
    """Verify an image meets quality standards.

    Args:
        image_path: Path to the image file.
        is_meme: If True, use relaxed dimension requirements.

    Returns:
        Tuple of (passed: bool, issues: list[str]).
    """
    issues = []

    if not image_path or not os.path.exists(image_path):
        return False, ["File does not exist"]

    # Size check
    file_size = os.path.getsize(image_path)
    if file_size < 50 * 1024:
        issues.append(f"File too small: {file_size // 1024}KB (min 50KB)")

    # Valid image check
    try:
        img = Image.open(image_path)
        w, h = img.size
        img.verify()
    except Exception as e:
        return False, [f"Invalid image file: {e}"]

    # Dimension check
    min_w, min_h = (400, 300) if is_meme else (800, 600)
    if w < min_w or h < min_h:
        issues.append(f"Too small: {w}x{h} (min {min_w}x{min_h})")

    # White background check
    try:
        img_check = Image.open(image_path).convert("RGB")
        pixels = img_check.resize((100, 100)).getdata()
        white_count = sum(1 for r, g, b in pixels if r > 240 and g > 240 and b > 240)
        white_ratio = white_count / len(pixels)
        if white_ratio > 0.55:
            issues.append(f"Mostly white background: {white_ratio:.0%} white pixels")
    except Exception:
        pass

    # Watermark domain check via .meta file
    meta_path = image_path + ".meta"
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r") as f:
                source_url = f.read().strip()
            if any(d in source_url.lower() for d in WATERMARK_DOMAINS):
                issues.append(f"Source is watermark domain: {source_url}")
        except Exception:
            pass

    return len(issues) == 0, issues


def fetch_image_for_scene(scene):
    """Fetch image(s) for a scene based on its visual_type.

    Args:
        scene: Scene dict with visual_type, image_search_query, image_search_queries.

    Returns:
        None for text-only scenes, a single path string for single-image scenes,
        or a list of paths for multi-image scenes (image_grid, image_collage).
    """
    visual_type = scene.get("visual_type", "text_bold")

    if visual_type in ("text_bold", "text_only"):
        return None

    if visual_type in ("fullscreen_image", "article_screenshot", "image_with_text"):
        query = scene.get("image_search_query", "")
        return fetch_image(query) if query else None

    if visual_type == "meme_fullscreen":
        query = scene.get("image_search_query", "")
        return fetch_image(query, is_meme=True) if query else None

    if visual_type in ("image_grid", "image_collage"):
        queries = scene.get("image_search_queries", [])
        query_fallback = scene.get("image_search_query", "")
        labels = scene.get("image_labels", [])
        paths = []
        for i, q in enumerate(queries):
            if q:
                paths.append(fetch_image(q))
            elif query_fallback or (i < len(labels) and labels[i]):
                label = labels[i] if i < len(labels) else ""
                paths.append(fetch_image(f"{query_fallback} {label}".strip()))
            else:
                paths.append(None)
        return paths

    # Unknown visual type — try single image
    query = scene.get("image_search_query", "")
    return fetch_image(query) if query else None


def fetch_and_verify_all(scenes, max_retries=3):
    """Fetch and verify images for all scenes, retrying failures.

    Args:
        scenes: List of scene dicts.
        max_retries: Max retry attempts per failed image (with modified queries).

    Returns:
        Dict mapping scene_id to image path(s) — single path or list of paths.
    """
    results = {}

    for scene in scenes:
        scene_id = scene.get("scene_id", 0)
        visual_type = scene.get("visual_type", "text_bold")

        if visual_type in ("text_bold", "text_only"):
            results[scene_id] = None
            continue

        is_meme = visual_type == "meme_fullscreen"

        image_result = fetch_image_for_scene(scene)

        if image_result is None:
            results[scene_id] = None
            continue

        # For single-image scenes
        if isinstance(image_result, str):
            passed, issues = verify_image(image_result, is_meme=is_meme)
            if passed:
                results[scene_id] = image_result
                continue

            # Retry with modified query
            query = scene.get("image_search_query", "")
            for attempt in range(max_retries):
                modified_query = f"{query} high quality" if attempt == 0 else f"{query} official {attempt + 1}"
                # Clear cached file to force re-download
                query_hash = hashlib.md5(modified_query.encode()).hexdigest()[:12]
                retry_path = os.path.join(IMAGE_CACHE_DIR, f"{query_hash}.jpg")
                if os.path.exists(retry_path):
                    os.remove(retry_path)

                new_path = fetch_image(modified_query, is_meme=is_meme)
                if new_path:
                    passed, issues = verify_image(new_path, is_meme=is_meme)
                    if passed:
                        results[scene_id] = new_path
                        break
            else:
                # Use best effort even if verification fails
                results[scene_id] = image_result
                print(f"  Scene {scene_id}: image verification failed after retries: {issues}")
            continue

        # For multi-image scenes (list of paths)
        if isinstance(image_result, list):
            verified_paths = []
            queries = scene.get("image_search_queries", [])
            for i, path in enumerate(image_result):
                if path is None:
                    verified_paths.append(None)
                    continue

                passed, issues = verify_image(path, is_meme=False)
                if passed:
                    verified_paths.append(path)
                    continue

                # Retry individual image
                original_query = queries[i] if i < len(queries) else ""
                retried = False
                for attempt in range(max_retries):
                    modified = f"{original_query} high quality" if attempt == 0 else f"{original_query} official {attempt + 1}"
                    q_hash = hashlib.md5(modified.encode()).hexdigest()[:12]
                    retry_p = os.path.join(IMAGE_CACHE_DIR, f"{q_hash}.jpg")
                    if os.path.exists(retry_p):
                        os.remove(retry_p)
                    new_p = fetch_image(modified)
                    if new_p:
                        p, _ = verify_image(new_p)
                        if p:
                            verified_paths.append(new_p)
                            retried = True
                            break
                if not retried:
                    verified_paths.append(path)  # best effort

            results[scene_id] = verified_paths

    return results
