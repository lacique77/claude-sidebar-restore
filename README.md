# claude-sidebar-restore

Restore lost **Claude Code** sessions in the Claude Desktop app sidebar after an uninstall, reinstall, or update wiped the session index.

> **This is for Claude Code (the AI coding assistant) sessions** — the ones that appear in the left sidebar when you use Claude Desktop in Code mode. It does NOT affect regular Claude chat conversations.

## The problem

You use **Claude Desktop** (the Windows/macOS app) in **Code mode** — the sidebar on the left shows all your previous Claude Code sessions. After an uninstall, reinstall, or auto-update, that sidebar goes blank. Every session appears gone.

They are not gone. The actual chat transcripts (`.jsonl` files in `~/.claude/projects/`) are **never deleted** — they survive the uninstall. Only the tiny pointer files the Desktop app sidebar reads are wiped. This script regenerates those pointer files so the sidebar shows all your sessions again.

This is a [known Anthropic bug](https://github.com/anthropics/claude-code/issues/29172) with multiple open reports ([#29373](https://github.com/anthropics/claude-code/issues/29373), [#25524](https://github.com/anthropics/claude-code/issues/25524), [#26452](https://github.com/anthropics/claude-code/issues/26452), [#31787](https://github.com/anthropics/claude-code/issues/31787), [#38691](https://github.com/anthropics/claude-code/issues/38691)). No official fix has shipped as of April 2026.

## What this script does

Reads every `.jsonl` transcript in `~/.claude/projects/` and generates a matching `local_<uuid>.json` pointer file in the Desktop app's session index folder. The app then shows all sessions in the sidebar again.

**Your transcripts are never modified.** The script only writes new pointer files. If anything looks wrong, just delete the generated files and you're back to the pre-run state.

## Requirements

- Python 3.8+ (standard library only — no `pip install` needed)
- Works on **Windows** (Store/MSIX and direct install), **macOS**, **Linux**

## Usage

> **Close the Claude Desktop app completely before running.**  
> If the app is open, it holds the index in memory and will overwrite your restored files when it exits.

```bash
# Auto-detect everything and restore all sessions
python restore_sidebar.py

# Preview what would be written without touching anything
python restore_sidebar.py --dry-run

# Test with 3 sessions first, then open the app to verify, then run the full restore
python restore_sidebar.py --pilot 3

# Specify a particular project folder (if you have multiple projects)
python restore_sidebar.py --project "/path/to/.claude/projects/my-project"

# Specify the target index folder manually (if auto-detect fails)
python restore_sidebar.py --target "/path/to/claude-code-sessions/<accountId>/<orgId>"
```

## Recommended steps

1. **Close Claude Desktop completely** (right-click tray icon → Quit, or `taskkill /F /IM claude.exe` on Windows)
2. Run `python restore_sidebar.py --pilot 3` to write 3 test entries
3. Open Claude Desktop and verify those 3 sessions appear in the sidebar
4. Close Claude Desktop again
5. Run `python restore_sidebar.py` for the full restore
6. Open Claude Desktop — all sessions should be back

## Session index locations

The script auto-detects these, but for reference:

| Platform | Path |
|---|---|
| Windows (Store) | `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude-code-sessions\<acct>\<org>\` |
| Windows (direct) | `%APPDATA%\Claude\claude-code-sessions\<acct>\<org>\` |
| macOS | `~/Library/Application Support/Claude/claude-code-sessions/<acct>/<org>/` |
| Linux | `~/.config/Claude/claude-code-sessions/<acct>/<org>/` |

## Schema

The generated `local_<uuid>.json` files match the format the app writes itself, verified by extracting and reading the app's source (`app.asar` → `.vite/build/index.js`):

```json
{
  "sessionId":              "local_<uuid>",
  "cliSessionId":           "<jsonl-filename-stem>",
  "cwd":                    "/path/to/project",
  "originCwd":              "/path/to/project",
  "userSelectedFolders":    [],
  "createdAt":              1234567890000,
  "lastActivityAt":         1234567890000,
  "model":                  "claude-opus-4-5",
  "effort":                 "medium",
  "isArchived":             false,
  "title":                  "First message from the session...",
  "permissionMode":         "acceptEdits",
  "remoteMcpServersConfig": [],
  "completedTurns":         12
}
```

Key invariant: **`sessionId` must equal the filename stem** (`local_<uuid>`). The app's `getSessionFilePath()` builds the path as `join(dir, sessionId + ".json")`.

## Safe to re-run

Already-indexed sessions are detected and skipped automatically. Re-running is always safe.

## Contributing

If you run into a case the script doesn't handle (different OS path, app update changed the schema, etc.), please open an issue with:
- Your OS and Claude Desktop version
- The output of the script with `--dry-run`
- The structure of a sample `local_*.json` file from the index folder (redact any personal content)

## Related issues

- [#29172](https://github.com/anthropics/claude-code/issues/29172) — sessions disappear after restart
- [#29373](https://github.com/anthropics/claude-code/issues/29373) — sessions lost after update (schema migration bug, workaround documented here)
- [#38691](https://github.com/anthropics/claude-code/issues/38691) — Windows reinstall, exact match
- [#25524](https://github.com/anthropics/claude-code/issues/25524), [#26452](https://github.com/anthropics/claude-code/issues/26452), [#31787](https://github.com/anthropics/claude-code/issues/31787) — recurring variants

## License

MIT
