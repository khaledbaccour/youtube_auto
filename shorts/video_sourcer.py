"""
Video sourcer — downloads YouTube videos via yt-dlp, extracts segments,
crops to 9:16 portrait for Shorts.
"""

import os
import re
import subprocess
import hashlib

from shorts_config import WIDTH, HEIGHT, OUTPUT_DIR


CLIPS_DIR = os.path.join(OUTPUT_DIR, "clips")
SOURCES_DIR = os.path.join(CLIPS_DIR, "sources")


def download_youtube_video(url, output_dir=None):
    """Download a YouTube video via yt-dlp. Returns local file path.

    Caches by video ID — won't re-download if already exists.
    """
    if output_dir is None:
        output_dir = SOURCES_DIR
    os.makedirs(output_dir, exist_ok=True)

    # Extract video ID for caching
    video_id = _extract_video_id(url)
    if not video_id:
        video_id = hashlib.md5(url.encode()).hexdigest()[:12]

    output_path = os.path.join(output_dir, f"{video_id}.mp4")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
        print(f"  Cached: {output_path}")
        return output_path

    print(f"  Downloading: {url}")
    cmd = [
        "yt-dlp",
        "-f", "best[height<=720]/best",
        "--no-playlist",
        "--no-warnings",
        "-o", output_path,
        url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        print(f"  yt-dlp error: {result.stderr[:300]}")
        return None

    if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
        print(f"  Downloaded: {output_path}")
        return output_path

    print("  Download failed — no output file")
    return None


def search_and_download(query, output_dir=None):
    """Search YouTube for a query and download the top result."""
    if output_dir is None:
        output_dir = SOURCES_DIR
    os.makedirs(output_dir, exist_ok=True)

    query_hash = hashlib.md5(query.encode()).hexdigest()[:12]
    output_path = os.path.join(output_dir, f"search_{query_hash}.mp4")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
        print(f"  Cached: {output_path}")
        return output_path

    print(f"  Searching YouTube: '{query}'")
    cmd = [
        "yt-dlp",
        f"ytsearch1:{query}",
        "-f", "best[height<=720]/best",
        "--no-playlist",
        "--no-warnings",
        "-o", output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        print(f"  yt-dlp search error: {result.stderr[:300]}")
        return None

    if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
        print(f"  Downloaded: {output_path}")
        return output_path

    print("  Search+download failed — no output file")
    return None


def extract_segment(video_path, start_s, end_s, output_path):
    """Extract a time segment from a video using ffmpeg.

    Returns output_path on success, None on failure.
    """
    if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        return output_path

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    duration = end_s - start_s

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_s),
        "-i", video_path,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast",
        "-an",  # strip audio
        "-loglevel", "error",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if result.returncode != 0:
        print(f"  ffmpeg extract error: {result.stderr[:200]}")
        return None

    return output_path


def prepare_clip(clip_path, target_duration):
    """Crop/resize a clip to 1080x1920 portrait, trim/loop to target duration.

    Returns path to the prepared clip.
    """
    prepared_path = clip_path.replace(".mp4", "_prepared.mp4")

    if os.path.exists(prepared_path) and os.path.getsize(prepared_path) > 1000:
        return prepared_path

    # Get source dimensions
    probe = _get_video_info(clip_path)
    if not probe:
        return clip_path

    src_w, src_h, src_dur = probe

    # Build ffmpeg filter for center-crop to 9:16
    target_ratio = WIDTH / HEIGHT  # 0.5625

    if src_w / src_h > target_ratio:
        # Source is wider — crop sides
        crop_h = src_h
        crop_w = int(src_h * target_ratio)
        crop_x = (src_w - crop_w) // 2
        crop_y = 0
    else:
        # Source is taller or exact — crop top/bottom
        crop_w = src_w
        crop_h = int(src_w / target_ratio)
        crop_x = 0
        crop_y = (src_h - crop_h) // 2

    # Build filter: crop then scale to target resolution
    vf = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={WIDTH}:{HEIGHT}"

    # Handle duration: trim if longer, loop if shorter
    input_args = ["-i", clip_path]
    if src_dur and src_dur < target_duration:
        # Loop the clip enough times
        loops = int(target_duration / src_dur) + 1
        input_args = ["-stream_loop", str(loops), "-i", clip_path]

    cmd = [
        "ffmpeg", "-y",
        *input_args,
        "-t", str(target_duration),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast",
        "-an",
        "-loglevel", "error",
        prepared_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if result.returncode != 0:
        print(f"  ffmpeg prepare error: {result.stderr[:200]}")
        return clip_path  # return original as fallback

    return prepared_path


def fetch_clips_for_script(script):
    """Fetch and prepare all video clips for a Shorts script.

    Returns ordered list of prepared clip paths (one per segment).
    """
    os.makedirs(CLIPS_DIR, exist_ok=True)

    source_video = script.get("source_video", {})
    url = source_video.get("url")
    search_query = source_video.get("search_query")

    # Download the source video
    source_path = None
    if url:
        source_path = download_youtube_video(url)
    if not source_path and search_query:
        source_path = search_and_download(search_query)

    if not source_path:
        print("  ERROR: Could not download source video")
        return []

    segments = script.get("segments", [])
    clip_paths = []

    for seg in segments:
        seg_id = seg.get("segment_id", 0)
        start = seg.get("video_start_s", 0)
        end = seg.get("video_end_s", start + 5)
        duration_hint = seg.get("duration_hint_s", end - start)

        # Extract segment from source
        seg_path = os.path.join(CLIPS_DIR, f"segment_{seg_id}.mp4")
        extracted = extract_segment(source_path, start, end, seg_path)

        if not extracted:
            print(f"  WARNING: Segment {seg_id} extraction failed, using source directly")
            extracted = source_path

        # Crop to portrait and trim to duration
        prepared = prepare_clip(extracted, duration_hint)
        clip_paths.append(prepared)
        print(f"  Segment {seg_id}: {prepared}")

    print(f"  Prepared {len(clip_paths)} clips")
    return clip_paths


def _extract_video_id(url):
    """Extract YouTube video ID from a URL."""
    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:shorts/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _get_video_info(path):
    """Get video width, height, duration using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration",
        "-show_entries", "format=duration",
        "-of", "json",
        path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return None

        import json
        data = json.loads(result.stdout)
        stream = data.get("streams", [{}])[0]
        fmt = data.get("format", {})

        w = stream.get("width", 0)
        h = stream.get("height", 0)
        dur = float(stream.get("duration", 0) or fmt.get("duration", 0) or 0)
        return w, h, dur
    except Exception:
        return None


if __name__ == "__main__":
    # Test: download reference short
    test_url = "https://www.youtube.com/shorts/us8jgWp3kns"
    path = download_youtube_video(test_url)
    if path:
        info = _get_video_info(path)
        print(f"  Video info: {info}")
