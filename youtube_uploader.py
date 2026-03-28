"""Upload videos to YouTube via the Data API v3."""

import os

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from youtube_analytics import authenticate
from database import update_video_youtube_id, update_video_status, get_video


def upload_video(video_id, video_path, title, description="", tags=None,
                 thumbnail_path=None, privacy="public", channel="shirefip"):
    """Upload video to YouTube via Data API v3.

    Args:
        video_id: local DB video id
        video_path: path to MP4 file
        title: video title
        description: video description
        tags: list of tag strings
        thumbnail_path: path to thumbnail image
        privacy: "public", "unlisted", or "private"
        channel: "shirefip" or "little_minds"

    Returns: youtube_video_id string
    """
    creds = authenticate(channel)
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": "28",  # Science & Technology
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  Upload progress: {int(status.progress() * 100)}%")

    youtube_video_id = response["id"]
    print(f"  Uploaded: https://youtube.com/watch?v={youtube_video_id}")

    # Set thumbnail if provided
    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            youtube.thumbnails().set(
                videoId=youtube_video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/png"),
            ).execute()
            print(f"  Thumbnail set.")
        except Exception as e:
            print(f"  Thumbnail upload failed (non-fatal): {e}")

    # Update database
    update_video_youtube_id(video_id, youtube_video_id)
    update_video_status(video_id, "published")

    return youtube_video_id
