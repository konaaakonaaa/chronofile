"""
Polling-based watcher. No inotify/watchdog dependency required, so it works
identically on Linux, macOS and Windows out of the box.
"""

from __future__ import annotations

import time

from .repo import Repo


def watch(repo: Repo, interval: float = None, on_snapshot=None, stop_after: float = None):
    """
    Poll the repo's directory forever (or until `stop_after` seconds elapse,
    useful for demos/tests), taking a snapshot whenever something changed.
    """
    interval = interval or repo.config().get("poll_interval", 2.0)
    started = time.time()

    print(f"Watching {repo.workdir} every {interval}s. Ctrl+C to stop.")
    try:
        while True:
            changes = repo.snapshot()
            if changes and on_snapshot:
                on_snapshot(changes)
            elif changes:
                for c in changes:
                    print(f"  [{c.kind}] {c.path}")
            if stop_after is not None and (time.time() - started) >= stop_after:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped watching.")
