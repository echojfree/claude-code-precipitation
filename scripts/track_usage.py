#!/usr/bin/env python3
"""Usage tracker for the Precipitation plugin.

Records tool and skill usage timestamps to enable skill lifecycle management
(active -> stale -> archived transitions). Also maintains curator state for
scheduling periodic consolidation runs.

State file: .claude/precip_state.json (per-project)

Hook Integration:
    When called from Claude Code hooks, the hook input JSON is provided on stdin.
    Use the "hook-event" subcommand to read stdin and auto-extract fields.
    The CLAUDE_PROJECT_DIR env var is used as the project path.

CLI Usage:
    python track_usage.py hook-event --source <skill|tool>
    python track_usage.py track --source <skill|tool> --name <name> \\
        --session <id> --project <path>
    python track_usage.py session-heartbeat --session <id> --project <path>
    python track_usage.py curator-check --project <path> [--interval-days 7]
    python track_usage.py curator-mark-run --project <path>
    python track_usage.py stats --project <path>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

STATE_FILE_NAME = ".claude/precip_state.json"
CURATOR_INTERVAL_DAYS = 7
STALE_AFTER_DAYS = 30
ARCHIVE_AFTER_DAYS = 90


# ---------------------------------------------------------------------------
# State file I/O
# ---------------------------------------------------------------------------

def _resolve_state_path(project_path: str) -> Path:
    """Resolve the state file path for a given project directory."""
    project = Path(project_path).resolve()
    for parent in [project] + list(project.parents):
        claude_dir = parent / ".claude"
        if claude_dir.is_dir():
            return claude_dir / "precip_state.json"
    claude_dir = project / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    return claude_dir / "precip_state.json"


def _load_state(state_path: Path) -> Dict[str, Any]:
    """Load state from disk, returning defaults if file doesn't exist."""
    if not state_path.exists():
        return _default_state()
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _default_state()
        base = _default_state()
        base.update(data)
        return base
    except (json.JSONDecodeError, OSError):
        return _default_state()


def _save_state(state_path: Path, data: Dict[str, Any]) -> None:
    """Atomically write state to disk."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)
        os.replace(tmp_path, state_path)
    except OSError:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _default_state() -> Dict[str, Any]:
    """Return default state structure."""
    return {
        "version": 1,
        "usage_log": {},
        "curator": {
            "last_run_at": None,
            "last_run_duration_seconds": None,
            "last_run_summary": None,
            "paused": False,
            "run_count": 0,
            "interval_days": CURATOR_INTERVAL_DAYS,
        },
        "lifecycle": {
            "stale_after_days": STALE_AFTER_DAYS,
            "archive_after_days": ARCHIVE_AFTER_DAYS,
        },
        "sessions": {},
        "precipitation": {
            "total_extractions": 0,
            "pending_reviews": 0,
            "last_precipitated_session": None,
        },
    }


# ---------------------------------------------------------------------------
# Hook stdin parser
# ---------------------------------------------------------------------------

def _read_hook_input() -> Optional[Dict[str, Any]]:
    """Read hook input JSON from stdin (provided by Claude Code hook executor).
    Returns None if stdin is empty or unreadable.
    """
    try:
        raw = sys.stdin.read()
        if not raw or not raw.strip():
            return None
        return json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return None


def _extract_fields(data: Dict[str, Any]) -> Dict[str, str]:
    """Extract tool_name and session_id from a PostToolUse/UserPromptSubmit
    hook input. Field names vary by hook event type.
    """
    result: Dict[str, str] = {}
    result["tool_name"] = data.get("tool_name", data.get("name", "unknown"))
    result["session_id"] = data.get("session_id", data.get("conversation_id", "unknown"))
    result["hook_event"] = data.get("hook_event_name", "unknown")
    return result


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_hook_event(args: argparse.Namespace) -> int:
    """Process a hook event from stdin. Extracts tool_name and session_id
    automatically from the hook input JSON, uses CLAUDE_PROJECT_DIR for
    project path.
    """
    hook_input = _read_hook_input()
    if hook_input is None:
        return 0

    fields = _extract_fields(hook_input)
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

    state_path = _resolve_state_path(project_dir)
    state = _load_state(state_path)
    now = datetime.now(timezone.utc).isoformat()

    name = fields["tool_name"]
    session_id = fields["session_id"]

    if name not in state["usage_log"]:
        state["usage_log"][name] = {
            "source": args.source,
            "first_used_at": now,
            "last_used_at": now,
            "use_count": 0,
            "sessions": [],
        }

    entry = state["usage_log"][name]
    entry["last_used_at"] = now
    entry["use_count"] += 1
    if session_id not in entry["sessions"]:
        entry["sessions"].append(session_id)
        if len(entry["sessions"]) > 50:
            entry["sessions"] = entry["sessions"][-50:]

    if session_id not in state["sessions"]:
        state["sessions"][session_id] = {
            "first_activity_at": now,
            "last_activity_at": now,
            "message_count": 0,
        }
    state["sessions"][session_id]["last_activity_at"] = now

    _save_state(state_path, state)
    return 0


def cmd_track(args: argparse.Namespace) -> int:
    """Record a tool or skill usage event (explicit CLI mode)."""
    state_path = _resolve_state_path(args.project)
    state = _load_state(state_path)
    now = datetime.now(timezone.utc).isoformat()

    name = args.name
    if name not in state["usage_log"]:
        state["usage_log"][name] = {
            "source": args.source,
            "first_used_at": now,
            "last_used_at": now,
            "use_count": 0,
            "sessions": [],
        }

    entry = state["usage_log"][name]
    entry["last_used_at"] = now
    entry["use_count"] += 1
    if args.session not in entry["sessions"]:
        entry["sessions"].append(args.session)
        if len(entry["sessions"]) > 50:
            entry["sessions"] = entry["sessions"][-50:]

    if args.session not in state["sessions"]:
        state["sessions"][args.session] = {
            "first_activity_at": now,
            "last_activity_at": now,
            "message_count": 0,
        }
    state["sessions"][args.session]["last_activity_at"] = now

    _save_state(state_path, state)
    return 0


def cmd_session_heartbeat(args: argparse.Namespace) -> int:
    """Update session last_activity_at timestamp."""
    state_path = _resolve_state_path(args.project)
    state = _load_state(state_path)
    now = datetime.now(timezone.utc).isoformat()

    if args.session not in state["sessions"]:
        state["sessions"][args.session] = {
            "first_activity_at": now,
            "last_activity_at": now,
            "message_count": 0,
        }
    state["sessions"][args.session]["last_activity_at"] = now
    state["sessions"][args.session]["message_count"] += 1

    _save_state(state_path, state)
    return 0


def cmd_curator_check(args: argparse.Namespace) -> int:
    """Check if curator should run. Prints 'run' or 'skip' to stdout."""
    state_path = _resolve_state_path(args.project)
    state = _load_state(state_path)
    curator = state["curator"]

    if curator.get("paused", False):
        print("skip: paused")
        return 0

    last_run = curator.get("last_run_at")
    if last_run is None:
        curator["last_run_at"] = datetime.now(timezone.utc).isoformat()
        _save_state(state_path, state)
        print("skip: first-run-seeded")
        return 0

    try:
        last_run_dt = datetime.fromisoformat(last_run)
        if last_run_dt.tzinfo is None:
            last_run_dt = last_run_dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        print("skip: invalid-timestamp")
        return 0

    interval = timedelta(days=args.interval_days)
    now = datetime.now(timezone.utc)
    if (now - last_run_dt) >= interval:
        print("run")
    else:
        print("skip: too-soon")

    return 0


def cmd_curator_mark_run(args: argparse.Namespace) -> int:
    """Mark curator as having completed a run."""
    state_path = _resolve_state_path(args.project)
    state = _load_state(state_path)
    now = datetime.now(timezone.utc).isoformat()

    state["curator"]["last_run_at"] = now
    state["curator"]["run_count"] += 1

    _save_state(state_path, state)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Print usage and precipitation statistics."""
    state_path = _resolve_state_path(args.project)
    state = _load_state(state_path)

    usage_log = state.get("usage_log", {})
    curator = state.get("curator", {})
    precip = state.get("precipitation", {})
    sessions = state.get("sessions", {})

    now = datetime.now(timezone.utc)
    stale_cutoff = (now - timedelta(days=STALE_AFTER_DAYS)).isoformat()
    archive_cutoff = (now - timedelta(days=ARCHIVE_AFTER_DAYS)).isoformat()

    active = 0
    stale = 0
    archived = 0
    for name, entry in usage_log.items():
        last_used = entry.get("last_used_at", "")
        if last_used < archive_cutoff:
            archived += 1
        elif last_used < stale_cutoff:
            stale += 1
        else:
            active += 1

    top_used = sorted(
        usage_log.items(),
        key=lambda x: x[1].get("use_count", 0),
        reverse=True,
    )[:10]

    output = {
        "usage": {
            "total_tracked": len(usage_log),
            "active": active,
            "stale": stale,
            "archived": archived,
            "top_10": [
                {"name": n, "use_count": e["use_count"], "last_used": e["last_used_at"]}
                for n, e in top_used
            ],
        },
        "curator": {
            "last_run_at": curator.get("last_run_at"),
            "run_count": curator.get("run_count", 0),
            "paused": curator.get("paused", False),
            "interval_days": curator.get("interval_days", CURATOR_INTERVAL_DAYS),
        },
        "precipitation": {
            "total_extractions": precip.get("total_extractions", 0),
            "pending_reviews": precip.get("pending_reviews", 0),
            "last_precipitated_session": precip.get("last_precipitated_session"),
        },
        "sessions": {
            "total": len(sessions),
            "recent": sum(
                1 for s in sessions.values()
                if s.get("last_activity_at", "") > stale_cutoff
            ),
        },
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_get_stale(args: argparse.Namespace) -> int:
    """List items that have become stale and should be reviewed."""
    state_path = _resolve_state_path(args.project)
    state = _load_state(state_path)
    usage_log = state.get("usage_log", {})

    now = datetime.now(timezone.utc)
    stale_cutoff = (now - timedelta(days=args.stale_days)).isoformat()
    archive_cutoff = (now - timedelta(days=args.archive_days)).isoformat()

    stale_items = []
    for name, entry in usage_log.items():
        last_used = entry.get("last_used_at", "")
        if last_used < archive_cutoff:
            stale_items.append({"name": name, "status": "ready_to_archive", "last_used": last_used})
        elif last_used < stale_cutoff:
            stale_items.append({"name": name, "status": "stale", "last_used": last_used})

    if stale_items:
        for item in stale_items:
            print(f"{item['status']}: {item['name']} (last used: {item['last_used']})")
    else:
        print("no-stale-items")

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Precipitation plugin usage tracker",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_he = sub.add_parser("hook-event", help="Process hook event from stdin")
    p_he.add_argument("--source", required=True, choices=["skill", "tool"])

    p_track = sub.add_parser("track", help="Record a usage event")
    p_track.add_argument("--source", required=True, choices=["skill", "tool"])
    p_track.add_argument("--name", required=True)
    p_track.add_argument("--session", required=True)
    p_track.add_argument("--project", required=True)

    p_hb = sub.add_parser("session-heartbeat", help="Update session heartbeat")
    p_hb.add_argument("--session", required=True)
    p_hb.add_argument("--project", required=True)

    p_cc = sub.add_parser("curator-check", help="Check if curator should run")
    p_cc.add_argument("--project", required=True)
    p_cc.add_argument("--interval-days", type=int, default=CURATOR_INTERVAL_DAYS)

    p_cm = sub.add_parser("curator-mark-run", help="Mark curator run complete")
    p_cm.add_argument("--project", required=True)

    p_stats = sub.add_parser("stats", help="Show precipitation statistics")
    p_stats.add_argument("--project", required=True)

    p_gs = sub.add_parser("get-stale", help="List stale items")
    p_gs.add_argument("--project", required=True)
    p_gs.add_argument("--stale-days", type=int, default=STALE_AFTER_DAYS)
    p_gs.add_argument("--archive-days", type=int, default=ARCHIVE_AFTER_DAYS)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    command_map = {
        "hook-event": cmd_hook_event,
        "track": cmd_track,
        "session-heartbeat": cmd_session_heartbeat,
        "curator-check": cmd_curator_check,
        "curator-mark-run": cmd_curator_mark_run,
        "stats": cmd_stats,
        "get-stale": cmd_get_stale,
    }

    handler = command_map.get(args.command)
    if handler:
        return handler(args)
    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
