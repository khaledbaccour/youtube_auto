"""Upload videos to Gofile.io for free hosting with web player."""

import os
import requests


def upload_to_gofile(video_path):
    """Upload a video file to Gofile.io.

    Returns the public download page URL (e.g. https://gofile.io/d/abc123),
    or None on failure.
    """
    if not os.path.isfile(video_path):
        print(f"[gofile] File not found: {video_path}")
        return None

    # Step 1: Get best server
    try:
        resp = requests.get("https://api.gofile.io/servers", timeout=10)
        data = resp.json()
        if data.get("status") != "ok" or not data.get("data", {}).get("servers"):
            print(f"[gofile] Failed to get server: {data}")
            return None
        server = data["data"]["servers"][0]["name"]
    except Exception as e:
        print(f"[gofile] Server lookup failed: {e}")
        return None

    # Step 2: Upload file
    try:
        print(f"[gofile] Uploading {os.path.basename(video_path)} to {server}...")
        with open(video_path, "rb") as f:
            resp = requests.post(
                f"https://{server}.gofile.io/contents/uploadfile",
                files={"file": (os.path.basename(video_path), f)},
                timeout=300,
            )
        data = resp.json()
        if data.get("status") == "ok":
            url = data["data"].get("downloadPage")
            print(f"[gofile] Upload success: {url}")
            return url
        else:
            print(f"[gofile] Upload failed: {data}")
            return None
    except Exception as e:
        print(f"[gofile] Upload error: {e}")
        return None
