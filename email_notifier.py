"""Gmail SMTP email notifications for youtube_auto pipeline."""

import smtplib
import traceback as tb_module
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders
import os

from config import GMAIL_ADDRESS, GMAIL_APP_PASSWORD, GMAIL_RECIPIENT

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


def _send_email(subject, html_body, attachments=None):
    """Send an email via Gmail SMTP with TLS.

    Args:
        subject: Email subject line.
        html_body: HTML string for the email body.
        attachments: Optional list of file paths to attach.
    """
    if not all([GMAIL_ADDRESS, GMAIL_APP_PASSWORD, GMAIL_RECIPIENT]):
        print("[email_notifier] Gmail credentials not configured, skipping email.")
        return False

    msg = MIMEMultipart()
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = GMAIL_RECIPIENT
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    for filepath in (attachments or []):
        if not os.path.isfile(filepath):
            continue
        with open(filepath, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{os.path.basename(filepath)}"',
        )
        msg.attach(part)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print(f"[email_notifier] Sent: {subject}")
        return True
    except Exception as exc:
        print(f"[email_notifier] Failed to send email: {exc}")
        return False


def send_review_email(video_id, title, topic, description="", script_summary="",
                      qa_report="", thumbnail_path=None, video_path=None,
                      base_url=None):
    """Send a pre-publish review email with inline thumbnail, video link, QA report,
    and approve/reject buttons.

    Args:
        video_id: Unique identifier for this video.
        title: Video title.
        topic: Topic string.
        description: Video description text.
        script_summary: First ~500 chars of the script narration.
        qa_report: QA report string (pass/fail details).
        thumbnail_path: Path to thumbnail image (embedded inline via CID).
        video_path: Path to the video file (uploaded to Gofile for public link).
        base_url: Public base URL for approve/reject buttons (default: localhost:5555).
    """
    summary = (script_summary or "")[:500]
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    approve_base = base_url or "http://localhost:5555"

    # Upload video to Gofile for public link
    video_link_html = ""
    if video_path and os.path.isfile(video_path):
        try:
            from video_uploader_gofile import upload_to_gofile
            gofile_url = upload_to_gofile(video_path)
        except Exception as e:
            print(f"[email_notifier] Gofile upload failed: {e}")
            gofile_url = None

        if gofile_url:
            video_link_html = f"""
            <tr><td style="padding:8px;font-weight:bold;color:#555;">Watch Video</td>
                <td style="padding:8px;"><a href="{gofile_url}"
                    style="color:#3b82f6;text-decoration:underline;font-weight:bold;">Watch on Gofile</a></td></tr>
            """
        else:
            abs_video = os.path.abspath(video_path).replace("\\", "/")
            video_link_html = f"""
            <tr><td style="padding:8px;font-weight:bold;color:#555;">Video File</td>
                <td style="padding:8px;"><a href="file:///{abs_video}"
                    style="color:#3b82f6;text-decoration:underline;">{os.path.basename(video_path)}</a> (local only)</td></tr>
            """

    # Inline thumbnail CID reference
    has_thumbnail = thumbnail_path and os.path.isfile(thumbnail_path)
    thumbnail_html = ""
    if has_thumbnail:
        thumbnail_html = """
        <div style="margin:16px 0;text-align:center;">
            <img src="cid:thumbnail" style="max-width:100%;border-radius:8px;border:2px solid #333;" />
        </div>
        """

    # Description section
    description_html = ""
    if description:
        description_html = f"""
        <h3 style="color:#555;">Description</h3>
        <p style="background:#f5f5f5;padding:12px;border-radius:6px;font-size:14px;line-height:1.5;">
            {description}
        </p>
        """

    # QA report section
    qa_html = ""
    if qa_report:
        qa_html = f"""
        <h3 style="color:#555;">QA Report</h3>
        <pre style="background:#1a1a2e;color:#e2e8f0;padding:12px;border-radius:6px;
                    font-size:13px;line-height:1.6;overflow-x:auto;white-space:pre-wrap;">{qa_report}</pre>
        """

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
        <h2 style="color:#333;font-size:22px;margin-bottom:4px;">{title}</h2>
        <p style="color:#999;font-size:13px;margin-top:0;">Video Ready for Review</p>
        {thumbnail_html}
        <table style="width:100%;border-collapse:collapse;">
            <tr><td style="padding:8px;font-weight:bold;color:#555;">Topic</td>
                <td style="padding:8px;">{topic}</td></tr>
            <tr><td style="padding:8px;font-weight:bold;color:#555;">Video ID</td>
                <td style="padding:8px;">{video_id}</td></tr>
            <tr><td style="padding:8px;font-weight:bold;color:#555;">Generated</td>
                <td style="padding:8px;">{timestamp}</td></tr>
            {video_link_html}
        </table>
        {description_html}
        <h3 style="color:#555;">Script Preview</h3>
        <p style="background:#f5f5f5;padding:12px;border-radius:6px;font-size:14px;line-height:1.5;">
            {summary}{"..." if len(script_summary or "") > 500 else ""}
        </p>
        {qa_html}
        <div style="text-align:center;margin:24px 0;">
            <a href="{approve_base}/approve/{video_id}"
               style="display:inline-block;padding:12px 32px;background:#22c55e;color:#fff;
                      text-decoration:none;border-radius:6px;font-weight:bold;font-size:16px;
                      margin-right:16px;">
                APPROVE
            </a>
            <a href="{approve_base}/reject/{video_id}"
               style="display:inline-block;padding:12px 32px;background:#ef4444;color:#fff;
                      text-decoration:none;border-radius:6px;font-weight:bold;font-size:16px;">
                REJECT
            </a>
        </div>
        <p style="color:#999;font-size:12px;">Approve/reject via: {approve_base}</p>
    </div>
    """

    # Build the email with inline thumbnail via CID
    if not all([GMAIL_ADDRESS, GMAIL_APP_PASSWORD, GMAIL_RECIPIENT]):
        print("[email_notifier] Gmail credentials not configured, skipping email.")
        return False

    msg = MIMEMultipart("related")
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = GMAIL_RECIPIENT
    msg["Subject"] = f"[Review] {title}"
    msg.attach(MIMEText(html, "html"))

    # Attach thumbnail inline with CID
    if has_thumbnail:
        with open(thumbnail_path, "rb") as f:
            img_data = f.read()
        ext = os.path.splitext(thumbnail_path)[1].lstrip(".").lower()
        if ext in ("jpg", "jpeg"):
            subtype = "jpeg"
        elif ext == "png":
            subtype = "png"
        else:
            subtype = "jpeg"
        img_part = MIMEImage(img_data, _subtype=subtype)
        img_part.add_header("Content-ID", "<thumbnail>")
        img_part.add_header("Content-Disposition", "inline", filename=os.path.basename(thumbnail_path))
        msg.attach(img_part)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print(f"[email_notifier] Sent: [Review] {title}")
        return True
    except Exception as exc:
        print(f"[email_notifier] Failed to send email: {exc}")
        return False


def send_error_alert(error_type, error_message, traceback_str=""):
    """Send an error notification email."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tb_block = f'<pre style="background:#1a1a1a;color:#f87171;padding:12px;border-radius:6px;overflow-x:auto;font-size:12px;">{traceback_str}</pre>' if traceback_str else ""

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
        <div style="background:#dc2626;color:#fff;padding:16px;border-radius:6px 6px 0 0;">
            <h2 style="margin:0;">Pipeline Error</h2>
        </div>
        <div style="border:1px solid #e5e5e5;border-top:none;padding:16px;border-radius:0 0 6px 6px;">
            <table style="width:100%;border-collapse:collapse;">
                <tr><td style="padding:8px;font-weight:bold;color:#555;">Type</td>
                    <td style="padding:8px;">{error_type}</td></tr>
                <tr><td style="padding:8px;font-weight:bold;color:#555;">Time</td>
                    <td style="padding:8px;">{timestamp}</td></tr>
                <tr><td style="padding:8px;font-weight:bold;color:#555;">Message</td>
                    <td style="padding:8px;color:#dc2626;">{error_message}</td></tr>
            </table>
            {tb_block}
        </div>
    </div>
    """
    return _send_email(f"[ERROR] {error_type}", html)


def send_daily_digest(videos_today, performance):
    """Send a daily summary of videos produced and channel performance.

    Args:
        videos_today: List of dicts with keys: title, status, score.
        performance: Dict with keys: avg_views, best_video, subs_gained.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    video_rows = ""
    for v in (videos_today or []):
        status_color = "#22c55e" if v.get("status") == "approved" else "#f59e0b"
        video_rows += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #eee;">{v.get("title", "Untitled")}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;color:{status_color};">{v.get("status", "unknown")}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;text-align:center;">{v.get("score", "N/A")}</td>
        </tr>"""

    if not video_rows:
        video_rows = '<tr><td colspan="3" style="padding:8px;color:#999;">No videos produced today.</td></tr>'

    avg_views = performance.get("avg_views", 0)
    best_video = performance.get("best_video", "N/A")
    subs_gained = performance.get("subs_gained", 0)

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
        <h2 style="color:#333;">Daily Digest — {timestamp}</h2>

        <h3 style="color:#555;">Videos Today</h3>
        <table style="width:100%;border-collapse:collapse;">
            <tr style="background:#f5f5f5;">
                <th style="padding:8px;text-align:left;">Title</th>
                <th style="padding:8px;text-align:left;">Status</th>
                <th style="padding:8px;text-align:center;">Score</th>
            </tr>
            {video_rows}
        </table>

        <h3 style="color:#555;margin-top:24px;">Channel Performance</h3>
        <table style="width:100%;border-collapse:collapse;">
            <tr><td style="padding:8px;font-weight:bold;color:#555;">Avg Views</td>
                <td style="padding:8px;">{avg_views}</td></tr>
            <tr><td style="padding:8px;font-weight:bold;color:#555;">Best Video</td>
                <td style="padding:8px;">{best_video}</td></tr>
            <tr><td style="padding:8px;font-weight:bold;color:#555;">Subs Gained</td>
                <td style="padding:8px;">+{subs_gained}</td></tr>
        </table>
    </div>
    """
    return _send_email(f"[Digest] YouTube Auto — {timestamp}", html)
