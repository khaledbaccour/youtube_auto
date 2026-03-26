"""Gmail SMTP email notifications for youtube_auto pipeline."""

import smtplib
import traceback as tb_module
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
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


def send_review_email(video_id, title, topic, script_summary, thumbnail_path=None):
    """Send a pre-publish review email with approve/reject buttons."""
    summary = (script_summary or "")[:500]
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    attachments = [thumbnail_path] if thumbnail_path and os.path.isfile(thumbnail_path) else []

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
        <h2 style="color:#333;">Video Ready for Review</h2>
        <table style="width:100%;border-collapse:collapse;">
            <tr><td style="padding:8px;font-weight:bold;color:#555;">Title</td>
                <td style="padding:8px;">{title}</td></tr>
            <tr><td style="padding:8px;font-weight:bold;color:#555;">Topic</td>
                <td style="padding:8px;">{topic}</td></tr>
            <tr><td style="padding:8px;font-weight:bold;color:#555;">Video ID</td>
                <td style="padding:8px;">{video_id}</td></tr>
            <tr><td style="padding:8px;font-weight:bold;color:#555;">Generated</td>
                <td style="padding:8px;">{timestamp}</td></tr>
        </table>
        <h3 style="color:#555;">Script Preview</h3>
        <p style="background:#f5f5f5;padding:12px;border-radius:6px;font-size:14px;line-height:1.5;">
            {summary}{"..." if len(script_summary or "") > 500 else ""}
        </p>
        <div style="text-align:center;margin:24px 0;">
            <a href="http://localhost:5555/approve/{video_id}"
               style="display:inline-block;padding:12px 32px;background:#22c55e;color:#fff;
                      text-decoration:none;border-radius:6px;font-weight:bold;font-size:16px;
                      margin-right:16px;">
                APPROVE
            </a>
            <a href="http://localhost:5555/reject/{video_id}"
               style="display:inline-block;padding:12px 32px;background:#ef4444;color:#fff;
                      text-decoration:none;border-radius:6px;font-weight:bold;font-size:16px;">
                REJECT
            </a>
        </div>
        <p style="color:#999;font-size:12px;">Buttons connect to the local scheduler on port 5555.</p>
    </div>
    """
    return _send_email(f"[Review] {title}", html, attachments)


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
