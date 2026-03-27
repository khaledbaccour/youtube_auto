"""
YouTube video research helpers — search, metadata, scene analysis, frame extraction.
Used by the video-researcher and clip-director agents.
"""

import os
import sys
import json
import subprocess
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shorts_config import OUTPUT_DIR


def search_youtube_videos(query, max_results=5):
    """Search YouTube via yt-dlp and return metadata for each result.

    Returns list of dicts: [{url, title, channel, view_count, like_count,
                             duration_s, upload_date, description}]
    """
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-download",
        "--flat-playlist",
        f"ytsearch{max_results}:{query}",
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            print(f"  yt-dlp search failed: {result.stderr[:200]}")
            return []
    except subprocess.TimeoutExpired:
        print("  yt-dlp search timed out")
        return []

    candidates = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            candidates.append({
                "url": data.get("webpage_url") or data.get("url", ""),
                "title": data.get("title", ""),
                "channel": data.get("channel") or data.get("uploader", ""),
                "view_count": data.get("view_count", 0) or 0,
                "like_count": data.get("like_count", 0) or 0,
                "duration_s": data.get("duration", 0) or 0,
                "upload_date": data.get("upload_date", ""),
                "description": (data.get("description") or "")[:300],
            })
        except json.JSONDecodeError:
            continue

    return candidates


def get_video_metadata(url):
    """Get detailed metadata for a single YouTube video without downloading."""
    cmd = ["yt-dlp", "--dump-json", "--no-download", url]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print(f"  yt-dlp metadata failed: {result.stderr[:200]}")
            return None
    except subprocess.TimeoutExpired:
        print("  yt-dlp metadata timed out")
        return None

    try:
        data = json.loads(result.stdout)
        return {
            "url": data.get("webpage_url", url),
            "title": data.get("title", ""),
            "channel": data.get("channel") or data.get("uploader", ""),
            "view_count": data.get("view_count", 0) or 0,
            "like_count": data.get("like_count", 0) or 0,
            "duration_s": data.get("duration", 0) or 0,
            "upload_date": data.get("upload_date", ""),
            "description": (data.get("description") or "")[:500],
            "thumbnail_url": data.get("thumbnail", ""),
            "categories": data.get("categories", []),
            "tags": data.get("tags", []),
        }
    except json.JSONDecodeError:
        return None


def analyze_video_segments(video_path, target_duration=45):
    """Analyze a video for high-energy segments using scene change detection.

    Returns list of (start_s, end_s, scene_change_count) sorted by activity.
    """
    # Get total duration
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        video_path,
    ]
    try:
        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=15)
        total_duration = float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError):
        print(f"  Could not probe duration for {video_path}")
        return []

    # Detect scene changes
    scene_cmd = [
        "ffmpeg", "-i", video_path,
        "-filter:v", "select='gt(scene,0.3)',showinfo",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            scene_cmd, capture_output=True, text=True, timeout=120
        )
        stderr = result.stderr
    except subprocess.TimeoutExpired:
        print("  Scene detection timed out, using even splits")
        return _even_splits(total_duration, target_duration)

    # Parse scene change timestamps
    scene_times = []
    for match in re.finditer(r"pts_time:([\d.]+)", stderr):
        scene_times.append(float(match.group(1)))

    if not scene_times:
        return _even_splits(total_duration, target_duration)

    # Score 5-second windows by scene change density
    window_size = 5.0
    windows = []
    t = 0.0
    while t + window_size <= total_duration:
        count = sum(1 for st in scene_times if t <= st < t + window_size)
        windows.append((t, t + window_size, count))
        t += window_size / 2  # 50% overlap

    # Sort by activity (most scene changes first)
    windows.sort(key=lambda w: w[2], reverse=True)

    # Select non-overlapping windows up to target duration
    selected = []
    total_selected = 0.0
    for start, end, count in windows:
        if total_selected >= target_duration:
            break
        # Check overlap with already selected
        overlaps = any(
            s < end and e > start for s, e, _ in selected
        )
        if not overlaps:
            selected.append((start, end, count))
            total_selected += end - start

    # Sort selected by time order
    selected.sort(key=lambda w: w[0])
    return selected


def _even_splits(total_duration, target_duration):
    """Fallback: split video evenly into segments."""
    num_segments = max(1, int(target_duration / 6))
    seg_duration = min(total_duration / num_segments, 8.0)
    spacing = total_duration / (num_segments + 1)
    segments = []
    for i in range(num_segments):
        start = spacing * (i + 1) - seg_duration / 2
        start = max(0, min(start, total_duration - seg_duration))
        segments.append((start, start + seg_duration, 1))
    return segments


def extract_hero_frame(video_path, timestamp_s, output_path):
    """Extract a single frame at a given timestamp."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    cmd = [
        "ffmpeg", "-ss", str(timestamp_s),
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        output_path,
        "-y",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"  Hero frame extracted: {output_path}")
            return output_path
    except subprocess.TimeoutExpired:
        pass

    print(f"  Failed to extract frame at {timestamp_s}s from {video_path}")
    return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"Searching: {query}")
        results = search_youtube_videos(query, max_results=3)
        print(json.dumps(results, indent=2))
    else:
        print("Usage: python shorts_research.py <search query>")
