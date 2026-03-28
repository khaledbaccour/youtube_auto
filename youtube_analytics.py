"""YouTube Data API + Analytics API integration for youtube_auto pipeline."""

import os
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import BASE_DIR, SHIREFIP_CHANNEL_ID, LITTLE_MINDS_CHANNEL_ID
from database import insert_analytics, get_connection, init_db

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # Required for thumbnail uploads
]
# NOTE: Adding new scopes requires deleting the existing token.json
# so the user re-authenticates with the expanded scope set.
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")

# Per-channel token files
TOKEN_PATHS = {
    "shirefip": os.path.join(BASE_DIR, "token_shirefip.json"),
    "little_minds": os.path.join(BASE_DIR, "token_little_minds.json"),
}
# Legacy fallback
LEGACY_TOKEN_PATH = os.path.join(BASE_DIR, "token.json")


def authenticate(channel="shirefip"):
    """OAuth2 flow: load cached token, refresh if expired, or run interactive flow.

    Args:
        channel: "shirefip" or "little_minds"
    """
    token_path = TOKEN_PATHS.get(channel, TOKEN_PATHS["shirefip"])

    # Migrate legacy token.json to token_shirefip.json if needed
    if channel == "shirefip" and not os.path.exists(token_path) and os.path.exists(LEGACY_TOKEN_PATH):
        os.rename(LEGACY_TOKEN_PATH, token_path)

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"OAuth credentials file not found at {CREDENTIALS_PATH}. "
                    "Download it from Google Cloud Console."
                )
            print(f"Authenticating for channel: {channel}")
            print(f"Select the '{channel}' channel when prompted in the browser.")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


def get_youtube_service(creds):
    """Build the YouTube Data API v3 service."""
    return build("youtube", "v3", credentials=creds)


def get_analytics_service(creds):
    """Build the YouTube Analytics API v2 service."""
    return build("youtubeAnalytics", "v2", credentials=creds)


def get_channel_id(channel="shirefip"):
    """Get the YouTube channel ID by name."""
    return {"shirefip": SHIREFIP_CHANNEL_ID, "little_minds": LITTLE_MINDS_CHANNEL_ID}[channel]


def list_channel_videos(youtube, max_results=50, channel="shirefip"):
    """Get videos from the channel's uploads playlist.

    Returns list of {youtube_video_id, title, published_at}.
    """
    channel_id = get_channel_id(channel)
    # Get the uploads playlist ID from the channel
    ch_resp = youtube.channels().list(
        part="contentDetails", id=channel_id
    ).execute()

    if not ch_resp.get("items"):
        print(f"No channel found for ID: {channel_id}")
        return []

    uploads_id = ch_resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    videos = []
    next_page = None
    while len(videos) < max_results:
        pl_resp = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_id,
            maxResults=min(50, max_results - len(videos)),
            pageToken=next_page,
        ).execute()

        for item in pl_resp.get("items", []):
            snippet = item["snippet"]
            videos.append({
                "youtube_video_id": snippet["resourceId"]["videoId"],
                "title": snippet["title"],
                "published_at": snippet["publishedAt"],
            })

        next_page = pl_resp.get("nextPageToken")
        if not next_page:
            break

    return videos


def fetch_video_analytics(analytics, video_id, start_date, end_date):
    """Fetch core metrics for a single video over a date range.

    Returns a dict of metric values.
    """
    resp = analytics.reports().query(
        ids="channel==MINE",
        startDate=start_date,
        endDate=end_date,
        metrics="views,estimatedMinutesWatched,averageViewDuration,likes,comments,subscribersGained,impressions,impressionClickThroughRate",
        filters=f"video=={video_id}",
    ).execute()

    rows = resp.get("rows", [])
    if not rows:
        return None

    row = rows[0]
    return {
        "views": int(row[0]),
        "watch_time_minutes": float(row[1]),
        "avg_view_duration_seconds": float(row[2]),
        "likes": int(row[3]),
        "comments": int(row[4]),
        "subs_gained": int(row[5]),
        "impressions": int(row[6]),
        "ctr": float(row[7]),
    }


def fetch_retention_data(analytics, video_id):
    """Fetch audience retention curve for a video.

    Returns dict with retention at key points (30s, 60s, end approximations).
    """
    resp = analytics.reports().query(
        ids="channel==MINE",
        startDate="2020-01-01",
        endDate=datetime.now().strftime("%Y-%m-%d"),
        metrics="audienceWatchRatio",
        dimensions="elapsedVideoTimeRatio",
        filters=f"video=={video_id}",
    ).execute()

    rows = resp.get("rows", [])
    if not rows:
        return {}

    retention = {}
    for row in rows:
        time_ratio = float(row[0])
        watch_ratio = float(row[1])

        # Map time ratios to approximate retention points
        if 0.09 <= time_ratio <= 0.11:
            retention["retention_30s"] = watch_ratio
        elif 0.19 <= time_ratio <= 0.21:
            retention["retention_60s"] = watch_ratio
        elif 0.95 <= time_ratio <= 1.0:
            retention["retention_end"] = watch_ratio

    return retention


def sync_all_analytics(channel="shirefip"):
    """Main entry point: authenticate, list videos, fetch + store analytics."""
    init_db()

    print(f"Authenticating with YouTube APIs for {channel}...")
    creds = authenticate(channel)
    youtube = get_youtube_service(creds)
    analytics_svc = get_analytics_service(creds)

    print(f"Fetching {channel} channel videos...")
    videos = list_channel_videos(youtube, channel=channel)
    print(f"Found {len(videos)} videos.")

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

    # Map youtube_video_id -> local DB video_id
    conn = get_connection()
    db_videos = conn.execute(
        "SELECT id, youtube_video_id FROM videos WHERE youtube_video_id IS NOT NULL"
    ).fetchall()
    conn.close()
    yt_to_db = {row["youtube_video_id"]: row["id"] for row in db_videos}

    synced = 0
    for v in videos:
        yt_id = v["youtube_video_id"]
        db_id = yt_to_db.get(yt_id)
        if not db_id:
            continue

        print(f"  Fetching analytics for: {v['title'][:50]}...")

        metrics = fetch_video_analytics(analytics_svc, yt_id, start_date, end_date)
        if not metrics:
            print(f"    No analytics data available.")
            continue

        retention = fetch_retention_data(analytics_svc, yt_id)
        metrics.update(retention)

        insert_analytics(db_id, end_date, metrics)
        synced += 1

    print(f"Synced analytics for {synced}/{len(videos)} videos.")


if __name__ == "__main__":
    sync_all_analytics()
