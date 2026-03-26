"""One-time script to register scheduler.py with Windows Task Scheduler (run on logon)."""

import os
import subprocess
import sys


def setup():
    python_exe = sys.executable
    scheduler_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduler.py")
    task_name = "YouTubeAutoScheduler"

    # Remove existing task if present (ignore errors)
    subprocess.run(
        ["schtasks", "/delete", "/tn", task_name, "/f"],
        capture_output=True,
    )

    # Create ONLOGON task
    result = subprocess.run(
        [
            "schtasks", "/create",
            "/tn", task_name,
            "/tr", f'"{python_exe}" "{scheduler_path}"',
            "/sc", "ONLOGON",
            "/rl", "LIMITED",
            "/f",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print(f"Task '{task_name}' registered successfully.")
        print(f"  Python: {python_exe}")
        print(f"  Script: {scheduler_path}")
        print("The scheduler will start automatically on next logon.")
    else:
        print(f"Failed to create task. Exit code: {result.returncode}")
        if result.stderr:
            print(f"Error: {result.stderr.strip()}")
        print("Try running this script as Administrator.")


if __name__ == "__main__":
    setup()
