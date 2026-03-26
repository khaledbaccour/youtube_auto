"""System tray scheduler with HTTP approve/reject server for youtube_auto."""

import json
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from config import BASE_DIR
from database import init_db, update_video_status
from email_notifier import send_error_alert

SCHEDULE_HOURS = [12, 14, 18]
STATE_FILE = os.path.join(BASE_DIR, "scheduler_state.json")
HTTP_PORT = 5555


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

class SchedulerState:
    def __init__(self):
        self.last_runs = {}  # "YYYY-MM-DD_HH" -> "completed"
        self.paused = False
        self._load()

    def _load(self):
        if os.path.isfile(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    data = json.load(f)
                self.last_runs = data.get("last_runs", {})
                self.paused = data.get("paused", False)
            except (json.JSONDecodeError, OSError):
                pass

    def save(self):
        with open(STATE_FILE, "w") as f:
            json.dump({"last_runs": self.last_runs, "paused": self.paused}, f, indent=2)

    def mark_completed(self, hour):
        key = datetime.now().strftime("%Y-%m-%d") + f"_{hour:02d}"
        self.last_runs[key] = "completed"
        self.save()

    def has_run(self, hour):
        key = datetime.now().strftime("%Y-%m-%d") + f"_{hour:02d}"
        return key in self.last_runs

    def get_missed_runs(self):
        """Return scheduled hours that have passed today without a run."""
        now = datetime.now()
        missed = []
        for h in SCHEDULE_HOURS:
            if h <= now.hour and not self.has_run(h):
                missed.append(h)
        return missed

    def get_next_scheduled(self):
        """Return the next scheduled hour today, or first hour tomorrow."""
        now = datetime.now()
        for h in SCHEDULE_HOURS:
            if h > now.hour:
                return h
        return SCHEDULE_HOURS[0]


# ---------------------------------------------------------------------------
# HTTP approve/reject server
# ---------------------------------------------------------------------------

class ApproveRejectHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.strip("/")
        parts = path.split("/", 1)

        if len(parts) == 2 and parts[0] in ("approve", "reject"):
            action = parts[0]
            video_id = parts[1]
            try:
                video_id_int = int(video_id)
                new_status = "approved" if action == "approve" else "rejected"
                update_video_status(video_id_int, new_status)
                color = "#22c55e" if action == "approve" else "#ef4444"
                label = "Approved" if action == "approve" else "Rejected"
                self._html_response(200, f"""
                    <div style="font-family:Arial,sans-serif;text-align:center;padding:60px;">
                        <h1 style="color:{color};">{label}</h1>
                        <p>Video #{video_id} has been {new_status}.</p>
                    </div>
                """)
            except ValueError:
                self._html_response(400, "<h1>Bad Request</h1><p>Invalid video ID.</p>")
            except Exception as exc:
                self._html_response(500, f"<h1>Error</h1><p>{exc}</p>")
        else:
            self._html_response(404, "<h1>Not Found</h1>")

    def _html_response(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(f"<html><body>{body}</body></html>".encode())

    def log_message(self, format, *args):
        pass  # suppress console logging


def _start_http_server():
    server = HTTPServer(("0.0.0.0", HTTP_PORT), ApproveRejectHandler)
    server.serve_forever()


# ---------------------------------------------------------------------------
# Tray icon
# ---------------------------------------------------------------------------

def _create_tray_icon():
    """Create a 64x64 PIL Image with red rounded rect and white 'YT' text."""
    img = Image.new("RGB", (64, 64), "black")
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([4, 4, 60, 60], radius=10, fill="#cc0000")
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "YT", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((64 - tw) / 2, (64 - th) / 2 - 2), "YT", fill="white", font=font)
    return img


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def _run_pipeline_safe(state):
    """Import and run the pipeline, catching errors."""
    try:
        from main import run_pipeline
        run_pipeline()
    except Exception:
        tb_str = traceback.format_exc()
        print(f"[scheduler] Pipeline error:\n{tb_str}")
        try:
            send_error_alert("Pipeline Failure", str(tb_str.splitlines()[-1]), tb_str)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Schedule loop
# ---------------------------------------------------------------------------

def _schedule_loop(state, update_menu_callback=None):
    """Check every 60s if it's time to run."""
    while True:
        if not state.paused:
            now = datetime.now()
            for h in SCHEDULE_HOURS:
                if now.hour == h and not state.has_run(h):
                    print(f"[scheduler] Scheduled run for {h}:00")
                    state.mark_completed(h)
                    _run_pipeline_safe(state)
                    if update_menu_callback:
                        update_menu_callback()
        time.sleep(60)


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def run_scheduler():
    """Start the scheduler: DB init, HTTP server, catch-up, schedule loop, tray icon."""
    import pystray

    init_db()
    state = SchedulerState()

    # Start HTTP server in background
    http_thread = threading.Thread(target=_start_http_server, daemon=True)
    http_thread.start()
    print(f"[scheduler] HTTP server on port {HTTP_PORT}")

    # Catch-up: run the most recent missed hour (max 1)
    missed = state.get_missed_runs()
    if missed:
        latest_missed = missed[-1]
        print(f"[scheduler] Catch-up run for missed {latest_missed}:00")
        state.mark_completed(latest_missed)
        threading.Thread(target=_run_pipeline_safe, args=(state,), daemon=True).start()

    # Build tray menu
    def get_next_label():
        h = state.get_next_scheduled()
        return f"Next: {h:02d}:00"

    def on_run_now(icon, item):
        threading.Thread(target=_run_pipeline_safe, args=(state,), daemon=True).start()

    def on_pause_toggle(icon, item):
        state.paused = not state.paused
        state.save()
        icon.update_menu()

    def pause_label(item):
        return "Resume" if state.paused else "Pause"

    def on_exit(icon, item):
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(get_next_label, None, enabled=False),
        pystray.MenuItem("Run Now", on_run_now),
        pystray.MenuItem(pause_label, on_pause_toggle),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", on_exit),
    )

    icon = pystray.Icon("youtube_auto", _create_tray_icon(), "YouTube Auto", menu)

    # Start schedule loop in background
    schedule_thread = threading.Thread(
        target=_schedule_loop,
        args=(state, lambda: icon.update_menu()),
        daemon=True,
    )
    schedule_thread.start()

    print("[scheduler] Running. Check system tray.")
    icon.run()  # blocks on main thread


if __name__ == "__main__":
    run_scheduler()
