from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from .repo import NotAChronofileRepo, Repo
from .watcher import watch as run_watch


def _get_repo() -> Repo:
    try:
        return Repo.find(Path.cwd())
    except NotAChronofileRepo as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_init(args):
    repo = Repo.init(Path.cwd(), poll_interval=args.interval)
    print(f"Initialized empty chronofile repo in {repo.store_dir}")


def cmd_watch(args):
    repo = _get_repo()
    run_watch(repo, interval=args.interval, stop_after=args.stop_after)


def cmd_snapshot(args):
    repo = _get_repo()
    changes = repo.snapshot(message=args.message)
    if not changes:
        print("No changes since last snapshot.")
        return
    for c in changes:
        print(f"  [{c.kind}] {c.path}")
    print(f"Snapshotted {len(changes)} file(s).")


def cmd_status(args):
    repo = _get_repo()
    statuses = [s for s in repo.status() if s.kind != "unchanged"]
    if not statuses:
        print("Nothing changed since last snapshot.")
        return
    for s in statuses:
        print(f"  [{s.kind}] {s.path}")


def cmd_log(args):
    repo = _get_repo()
    hist = repo.history(args.path)
    if not hist:
        print(f"No history for {args.path}")
        return
    for row in reversed(hist):
        ts = row["timestamp"]
        import datetime
        when = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        tag = "DELETED" if row["deleted"] else row["hash"][:10]
        msg = f" - {row['message']}" if row["message"] else ""
        print(f"rev {row['revision']:>4}  {when}  {tag}  ({row['size']} bytes){msg}")


def cmd_diff(args):
    repo = _get_repo()
    try:
        old = repo.read_revision(args.path, args.rev1).decode("utf-8", errors="replace")
        new = repo.read_revision(args.path, args.rev2).decode("utf-8", errors="replace")
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"{args.path}@{args.rev1 or 'prev'}",
        tofile=f"{args.path}@{args.rev2 or 'latest'}",
    )
    sys.stdout.writelines(diff)


def cmd_restore(args):
    repo = _get_repo()
    try:
        repo.restore(args.path, args.revision, backup_current=not args.no_backup)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Restored {args.path} to revision {args.revision or 'latest'}")


def cmd_show(args):
    repo = _get_repo()
    try:
        content = repo.read_revision(args.path, args.revision)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    sys.stdout.buffer.write(content)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="chronofile", description="A time machine for your files.")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("init", help="Initialize a chronofile repo in the current directory")
    sp.add_argument("--interval", type=float, default=2.0, help="poll interval in seconds for `watch`")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("watch", help="Watch the directory and snapshot on change")
    sp.add_argument("--interval", type=float, default=None)
    sp.add_argument("--stop-after", type=float, default=None, help="stop after N seconds (for demos/tests)")
    sp.set_defaults(func=cmd_watch)

    sp = sub.add_parser("snapshot", help="Take a one-off snapshot now")
    sp.add_argument("-m", "--message", default=None)
    sp.set_defaults(func=cmd_snapshot)

    sp = sub.add_parser("status", help="Show what's changed since the last snapshot")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("log", help="Show revision history for a file")
    sp.add_argument("path")
    sp.set_defaults(func=cmd_log)

    sp = sub.add_parser("diff", help="Diff two revisions of a file")
    sp.add_argument("path")
    sp.add_argument("rev1", nargs="?", default="-2")
    sp.add_argument("rev2", nargs="?", default="-1")
    sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("restore", help="Restore a file to a past revision")
    sp.add_argument("path")
    sp.add_argument("revision", nargs="?", default=None)
    sp.add_argument("--no-backup", action="store_true", help="don't snapshot current state first")
    sp.set_defaults(func=cmd_restore)

    sp = sub.add_parser("show", help="Print the content of a file at a given revision")
    sp.add_argument("path")
    sp.add_argument("revision", nargs="?", default=None)
    sp.set_defaults(func=cmd_show)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
