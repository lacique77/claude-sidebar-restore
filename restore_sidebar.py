#!/usr/bin/env python3
"""
restore_sidebar.py
==================
Restores the Claude Desktop app sidebar session list after an uninstall,
reinstall, or update that wiped the session index.

The actual chat transcripts (.jsonl files) are never touched — they survive
uninstalls. Only the tiny pointer files the sidebar reads are regenerated.

Supports: Windows (Store/MSIX and direct install), macOS, Linux.
Requires: Python 3.8+, standard library only (no pip installs).

Usage:
    python restore_sidebar.py                  # auto-detect everything
    python restore_sidebar.py --dry-run        # preview without writing
    python restore_sidebar.py --pilot 3        # write 3 files to test first
    python restore_sidebar.py --project path   # use a specific project folder
    python restore_sidebar.py --help
"""

import argparse
import json
import os
import platform
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Platform-specific paths
# ---------------------------------------------------------------------------

def find_claude_projects_dirs() -> list[Path]:
    """
    Return all project directories found under ~/.claude/projects/.
    Each subdirectory is one project (named after its sanitised path).
    """
    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        return []
    return [d for d in base.iterdir() if d.is_dir()]


def find_session_index_dirs() -> list[Path]:
    """
    Return candidate session index directories for the Desktop app.
    These are the folders the app reads local_*.json files from.

    Structure: <app-data>/Claude/claude-code-sessions/<accountId>/<orgId>/
    """
    candidates: list[Path] = []
    system = platform.system()

    if system == "Darwin":
        # macOS
        base = Path.home() / "Library" / "Application Support" / "Claude" / "claude-code-sessions"
        _collect_leaf_dirs(base, candidates)

    elif system == "Windows":
        local_app = Path(os.environ.get("LOCALAPPDATA", ""))
        roaming_app = Path(os.environ.get("APPDATA", ""))

        # Windows Store / MSIX install — package folder under LocalAppData\Packages
        packages_dir = local_app / "Packages"
        if packages_dir.exists():
            for pkg in packages_dir.iterdir():
                if pkg.name.startswith("Claude_") and pkg.is_dir():
                    msix_base = pkg / "LocalCache" / "Roaming" / "Claude" / "claude-code-sessions"
                    _collect_leaf_dirs(msix_base, candidates)

        # Windows direct (non-Store) install — AppData\Roaming\Claude
        direct_base = roaming_app / "Claude" / "claude-code-sessions"
        _collect_leaf_dirs(direct_base, candidates)

    else:
        # Linux / other — XDG config dir
        xdg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        base = xdg / "Claude" / "claude-code-sessions"
        _collect_leaf_dirs(base, candidates)

    return candidates


def _collect_leaf_dirs(base: Path, out: list[Path]) -> None:
    """Walk two levels deep (accountId/orgId) and collect leaf dirs."""
    if not base.exists():
        return
    try:
        for acct_dir in base.iterdir():
            if not acct_dir.is_dir():
                continue
            try:
                for org_dir in acct_dir.iterdir():
                    if org_dir.is_dir():
                        out.append(org_dir)
            except PermissionError:
                pass
    except PermissionError:
        pass


# ---------------------------------------------------------------------------
# JSONL parsing
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_SKIP_PREFIXES = ("Caveat:", "DO NOT respond")
DEFAULT_MODEL = "claude-opus-4-5"


def _iso_to_ms(ts: str) -> int | None:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def parse_jsonl(path: Path, cwd_override: str | None = None) -> dict:
    """
    Read a .jsonl session transcript and extract sidebar metadata.
    Returns {} if the file has no usable data.
    """
    title = ""
    model = DEFAULT_MODEL
    created_at = None
    last_activity_at = None
    completed_turns = 0
    cwd = cwd_override or ""

    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
    except Exception as e:
        print(f"  WARN  cannot read {path.name}: {e}")
        return {}

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue

        # Timestamps
        ts = _iso_to_ms(entry.get("timestamp", ""))
        if ts:
            if created_at is None:
                created_at = ts
            last_activity_at = ts

        etype = entry.get("type", "")

        # cwd — some entries carry it directly
        if not cwd and entry.get("cwd"):
            cwd = entry["cwd"]

        # Title: first real human message (strip XML tags, skip system caveats)
        if not title and etype == "user":
            msg = entry.get("message", {})
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    b.get("text", "")
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            content = _TAG_RE.sub("", str(content))
            content = re.sub(r"\s{2,}", " ", content.replace("\n", " ")).strip()
            if any(content.startswith(p) for p in _SKIP_PREFIXES):
                continue
            if content:
                title = content[:120]

        # Model + turn count from assistant messages
        if etype == "assistant":
            msg = entry.get("message", {})
            if isinstance(msg, dict) and msg.get("model"):
                model = msg["model"]
            completed_turns += 1

    if created_at is None:
        return {}

    return {
        "title":          title or f"Session {path.stem[:20]}",
        "model":          model,
        "cwd":            cwd,
        "createdAt":      created_at,
        "lastActivityAt": last_activity_at or created_at,
        "completedTurns": completed_turns,
    }


# ---------------------------------------------------------------------------
# Core restore logic
# ---------------------------------------------------------------------------

def restore(
    project_dir: Path,
    target_dir: Path,
    dry_run: bool = False,
    pilot: int = 0,
) -> tuple[int, int, int]:
    """
    Restore sidebar index files for one project directory into target_dir.
    Returns (written, skipped, failed).
    """
    jsonl_files = sorted(project_dir.glob("*.jsonl"))
    if not jsonl_files:
        print(f"  No .jsonl files found in {project_dir}")
        return 0, 0, 0

    # Read existing index to skip already-indexed sessions
    existing_cli_ids: set[str] = set()
    if target_dir.exists():
        for f in target_dir.glob("local_*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                cli_id = data.get("cliSessionId", "")
                if cli_id:
                    existing_cli_ids.add(cli_id)
            except Exception:
                pass

    print(f"  Source  : {project_dir}  ({len(jsonl_files)} transcripts)")
    print(f"  Target  : {target_dir}")
    print(f"  Already indexed: {len(existing_cli_ids)} sessions (will skip)")
    if dry_run:
        print("  DRY RUN — no files will be written")
    print()

    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    written = skipped = failed = 0
    # Infer cwd from the project folder name (C--Automation-docre-system -> C:\Automation\docre-system)
    cwd_guess = _dir_name_to_path(project_dir.name)

    for jsonl_path in jsonl_files:
        cli_id = jsonl_path.stem

        if cli_id in existing_cli_ids:
            skipped += 1
            continue

        meta = parse_jsonl(jsonl_path, cwd_override=cwd_guess)
        if not meta:
            print(f"  SKIP  {jsonl_path.name} -- no usable data")
            failed += 1
            continue

        cwd = meta["cwd"] or cwd_guess
        session_uuid = uuid.uuid4()

        payload = {
            "sessionId":              f"local_{session_uuid}",
            "cliSessionId":           cli_id,
            "cwd":                    cwd,
            "originCwd":              cwd,
            "userSelectedFolders":    [],
            "createdAt":              meta["createdAt"],
            "lastActivityAt":         meta["lastActivityAt"],
            "model":                  meta["model"],
            "effort":                 "medium",
            "isArchived":             False,
            "title":                  meta["title"],
            "permissionMode":         "acceptEdits",
            "remoteMcpServersConfig": [],
            "completedTurns":         meta["completedTurns"],
        }

        out_path = target_dir / f"local_{session_uuid}.json"
        date_str = datetime.fromtimestamp(
            meta["createdAt"] / 1000, tz=timezone.utc
        ).strftime("%b %d")
        label = f"  {'DRY' if dry_run else 'OK ':3s}  [{date_str}]  {cli_id[:8]}...  \"{meta['title'][:55]}\""

        if not dry_run:
            out_path.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )

        print(label)
        written += 1

        if pilot and written >= pilot:
            print(f"\n  Pilot limit reached ({pilot}). Stopping.")
            break

    return written, skipped, failed


def _dir_name_to_path(name: str) -> str:
    """
    Convert ~/.claude/projects/ subdirectory name back to a filesystem path.
    Claude Code encodes paths as: separators become '-', drive colon becomes '-'.
    e.g. 'C--Automation-docre-system' -> 'C:\\Automation\\docre-system' on Windows
         '-home-user-myproject'       -> '/home/user/myproject' on Linux/macOS
    """
    if not name:
        return ""
    # Leading '-' means Unix absolute path starting with /
    if name.startswith("-"):
        return name.replace("-", "/")
    # Windows drive letter pattern: X-- -> X:\
    if len(name) >= 3 and name[1:3] == "--":
        rest = name[3:].replace("-", "\\")
        return f"{name[0]}:\\{rest}"
    # Fallback: treat dashes as separators
    return name.replace("-", os.sep)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restore Claude Desktop app sidebar sessions from .jsonl transcripts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python restore_sidebar.py                  # auto-detect and restore everything
  python restore_sidebar.py --dry-run        # preview without writing anything
  python restore_sidebar.py --pilot 3        # write 3 sessions to test, verify in app, then re-run without --pilot
  python restore_sidebar.py --project /path/to/.claude/projects/my-project
        """,
    )
    parser.add_argument(
        "--project",
        metavar="PATH",
        help="Path to a specific .jsonl project folder (default: auto-detect all)",
    )
    parser.add_argument(
        "--target",
        metavar="PATH",
        help="Path to the session index folder (default: auto-detect)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be written without creating any files",
    )
    parser.add_argument(
        "--pilot",
        metavar="N",
        type=int,
        default=0,
        help="Write only N sessions (test before full run)",
    )
    args = parser.parse_args()

    print("=" * 62)
    print("Claude Desktop Sidebar Restore")
    print("=" * 62)
    print(f"Platform : {platform.system()} {platform.release()}")
    print()

    # Resolve project directories
    if args.project:
        project_dirs = [Path(args.project)]
        if not project_dirs[0].exists():
            print(f"ERROR: --project path not found: {project_dirs[0]}")
            sys.exit(1)
    else:
        project_dirs = find_claude_projects_dirs()
        if not project_dirs:
            print("ERROR: No project directories found under ~/.claude/projects/")
            print("       Pass --project <path> to specify a folder manually.")
            sys.exit(1)
        print(f"Found {len(project_dirs)} project folder(s) under ~/.claude/projects/")

    # Resolve target directory
    if args.target:
        target_dirs = [Path(args.target)]
    else:
        target_dirs = find_session_index_dirs()
        if not target_dirs:
            print("ERROR: Cannot find the Claude Desktop session index folder.")
            print("       Make sure Claude Desktop is installed, then pass --target <path>.")
            print()
            print("Expected locations:")
            print("  Windows Store : AppData/Local/Packages/Claude_*/LocalCache/Roaming/Claude/claude-code-sessions/<acct>/<org>/")
            print("  Windows direct: AppData/Roaming/Claude/claude-code-sessions/<acct>/<org>/")
            print("  macOS         : ~/Library/Application Support/Claude/claude-code-sessions/<acct>/<org>/")
            sys.exit(1)
        print(f"Found {len(target_dirs)} session index folder(s)")

    if len(target_dirs) > 1:
        print()
        print("Multiple session index folders found (multiple accounts or installs):")
        for i, d in enumerate(target_dirs):
            count = len(list(d.glob("local_*.json"))) if d.exists() else 0
            print(f"  [{i}] {d}  ({count} existing entries)")
        print()
        print("Using the first one. Pass --target <path> to choose a specific one.")
        target_dirs = [target_dirs[0]]

    target_dir = target_dirs[0]

    print()
    print("-" * 62)

    total_written = total_skipped = total_failed = 0

    for project_dir in project_dirs:
        w, s, f = restore(
            project_dir=project_dir,
            target_dir=target_dir,
            dry_run=args.dry_run,
            pilot=args.pilot,
        )
        total_written += w
        total_skipped += s
        total_failed += f
        print()

    print("=" * 62)
    print(f"Written : {total_written} new index entries")
    print(f"Skipped : {total_skipped} already indexed")
    print(f"Failed  : {total_failed} unreadable files")
    print("=" * 62)

    if total_written > 0 and not args.dry_run:
        print()
        if args.pilot:
            print(f"Pilot complete. Open Claude Desktop and check the sidebar.")
            print(f"If those {total_written} session(s) appear, close the app and re-run without --pilot.")
        else:
            print("Done. Start Claude Desktop — all sessions should appear in the sidebar.")
    elif args.dry_run and total_written > 0:
        print()
        print(f"Dry run complete. Re-run without --dry-run to write {total_written} entries.")


if __name__ == "__main__":
    main()
