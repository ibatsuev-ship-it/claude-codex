#!/usr/bin/env python3
"""
PostToolUse hook for codex MCP — detects auto-compaction events and surfaces them.

Triggered after every mcp__codex__codex / mcp__codex__codex-reply tool call.
Scans ~/.codex/sessions/**/rollout-*.jsonl for new "context_compacted" /
"compacted" events since the previous run, using a per-file (offset, mtime)
watermark persisted at ~/.cache/claude-codex-compact-watcher/state.json.

Design:
- mtime-skip: files whose mtime did not change since last hook are skipped
  without any I/O on file body. O(1) stat() per file is cheap even at hundreds.
- offset-tail: when a file did change, read only the appended bytes since
  the recorded offset.
- first-run: record all current rollouts at their current size, no notifications
  for historical events.
- new files appearing later: snapshot at first sight, also no historical noise.

Robustness contract:
- Never raises uncaught exceptions (would break the hook output).
- Always emits a single valid JSON object to stdout.
- On internal error: emit empty {} so the hook is a no-op for that turn.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

SESSIONS_DIR = Path.home() / ".codex" / "sessions"
STATE_DIR = Path.home() / ".cache" / "claude-codex-compact-watcher"
STATE_FILE = STATE_DIR / "state.json"


def emit(obj: dict) -> None:
    """Print JSON output for the hook and exit cleanly."""
    try:
        sys.stdout.write(json.dumps(obj))
    except Exception:
        sys.stdout.write("{}")
    sys.stdout.flush()
    sys.exit(0)


def load_state() -> dict:
    try:
        with STATE_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    return {}


def save_state_atomic(state: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".state.", dir=str(STATE_DIR))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh, separators=(",", ":"))
            os.replace(tmp_path, STATE_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except Exception:
        pass


def find_all_rollouts() -> list[Path]:
    if not SESSIONS_DIR.is_dir():
        return []
    out: list[Path] = []
    try:
        for p in SESSIONS_DIR.rglob("rollout-*.jsonl"):
            try:
                if p.is_file():
                    out.append(p)
            except OSError:
                continue
    except Exception:
        return []
    return out


def is_compaction_event(line: str) -> bool:
    """Return True iff the JSONL line represents a compaction event."""
    if "compact" not in line:  # cheap pre-filter
        return False
    try:
        ev = json.loads(line)
    except Exception:
        return False
    if not isinstance(ev, dict):
        return False
    if ev.get("type") == "compacted":
        return True
    payload = ev.get("payload")
    if isinstance(payload, dict) and payload.get("type") == "context_compacted":
        return True
    return False


def scan_file_for_new_compactions(
    path: Path, last_offset: int
) -> tuple[int, list[str]]:
    """
    Read from `last_offset` to EOF, return (new_offset, [iso_timestamps_of_new_events]).
    If file shrank (rotation/truncation), restart from 0.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return last_offset, []

    if size < last_offset:
        last_offset = 0  # rotated/truncated

    if size == last_offset:
        return last_offset, []

    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            fh.seek(last_offset)
            buf = fh.read()
    except OSError:
        return last_offset, []

    # Process whole-line chunks only — never act on a half-written line.
    last_newline = buf.rfind("\n")
    if last_newline < 0:
        return last_offset, []  # no complete line yet
    consumed = buf[: last_newline + 1]
    new_offset = last_offset + len(consumed.encode("utf-8", errors="replace"))

    new_events: list[str] = []
    for line in consumed.splitlines():
        line = line.strip()
        if not line:
            continue
        if not is_compaction_event(line):
            continue
        try:
            ev = json.loads(line)
            ts = ev.get("timestamp") or (
                ev.get("payload", {}) if isinstance(ev.get("payload"), dict) else {}
            ).get("timestamp") or ""
        except Exception:
            ts = ""
        new_events.append(ts or "<unknown-time>")

    return new_offset, new_events


def main() -> None:
    # Drain stdin to be safe with large hook payloads.
    try:
        sys.stdin.read()
    except Exception:
        pass

    try:
        rollouts = find_all_rollouts()
        first_run = not STATE_FILE.exists()
        state = load_state()
        new_state: dict[str, dict] = {}
        all_new: list[tuple[str, str]] = []  # (basename, timestamp)

        for path in rollouts:
            key = str(path)
            try:
                stat = path.stat()
                cur_size = stat.st_size
                cur_mtime = stat.st_mtime
            except OSError:
                continue

            prev = state.get(key)

            # First-run OR new-file: snapshot, no scan, no report.
            if first_run or not isinstance(prev, dict) or "offset" not in prev:
                new_state[key] = {"offset": cur_size, "mtime": cur_mtime}
                continue

            try:
                last_offset = int(prev["offset"])
            except (TypeError, ValueError):
                last_offset = cur_size
            try:
                last_mtime = float(prev.get("mtime", 0.0))
            except (TypeError, ValueError):
                last_mtime = 0.0

            # mtime-skip: nothing happened to this file → carry forward as-is.
            if cur_mtime == last_mtime and cur_size == last_offset:
                new_state[key] = {"offset": last_offset, "mtime": last_mtime}
                continue

            new_offset, events = scan_file_for_new_compactions(path, last_offset)
            new_state[key] = {"offset": new_offset, "mtime": cur_mtime}
            for ts in events:
                all_new.append((path.name, ts))

        # GC orphaned state entries (files that no longer exist on disk).
        live = {str(p) for p in rollouts}
        for key in list(state.keys()):
            if key in live:
                continue
            try:
                if not Path(key).is_file():
                    continue  # already excluded from new_state
            except Exception:
                continue
            # Otherwise: file exists but rglob missed it (e.g. permissions).
            # Carry forward to avoid re-snapshot on next run.
            new_state.setdefault(key, state[key])

        save_state_atomic(new_state)

        if first_run or not all_new:
            emit({})
            return

        # Build human-readable notification (cap noise at 3 events).
        sample = all_new[:3]
        more = len(all_new) - len(sample)
        lines = [f"  - {ts}  ({name})" for name, ts in sample]
        if more > 0:
            lines.append(f"  - ... and {more} more")
        joined = "\n".join(lines)

        plural = "s" if len(all_new) != 1 else ""
        user_msg = (
            f"codex auto-compacted its context ({len(all_new)} event{plural}). "
            f"Cache warms back up on next reply.\n{joined}"
        )
        claude_ctx = (
            f"[codex-compact-watcher] codex compacted its conversation context "
            f"during the last tool call ({len(all_new)} compaction event{plural} "
            f"appeared in the rollout log).\n"
            f"Implications:\n"
            f"  1) Historical detail before the compaction now lives only as a summary inside the codex thread.\n"
            f"  2) The OpenAI prompt cache for that thread is partially invalidated, so the next "
            f"codex-reply will be slower than usual until the cache reheats.\n"
            f"  3) If the user asks codex about something detailed from earlier in this thread, "
            f"verify codex still has it before relying on the answer.\n"
            f"Events:\n{joined}"
        )

        emit(
            {
                "systemMessage": user_msg,
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": claude_ctx,
                },
            }
        )
    except Exception:
        emit({})


if __name__ == "__main__":
    main()
