"""Run every saved search once, or leave this process open for a daily run."""

from __future__ import annotations

import os
import sys
import time

from job_matchmaker.notifier import load_env
from job_matchmaker.service import run_saved_profiles


def run_once() -> None:
    for line in run_saved_profiles():
        print(line)


def main() -> None:
    load_env()
    if "--loop" in sys.argv:
        import schedule

        run_at = os.getenv("RUN_AT", "09:00")
        schedule.every().day.at(run_at).do(run_once)
        print(f"Running saved searches now, then every day at {run_at}. Press Ctrl+C to stop.")
        run_once()
        while True:
            schedule.run_pending()
            time.sleep(30)
        return
    run_once()


if __name__ == "__main__":
    main()
