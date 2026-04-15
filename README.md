# claude-sidebar-restore

Restore lost **Claude Code** sessions in the Claude Desktop app sidebar after an uninstall, reinstall, or update wiped the session index.

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
python restore_sidebar.py --project "C:\Users\YourName\.claude\projects\my-project"

# If auto-detect fails, see "Finding the session index folder manually" below
python restore_sidebar.py --target "<paste the folder path here>"
```

## Recommended steps

1. **Close Claude Desktop completely** (right-click tray icon → Quit, or `taskkill /F /IM claude.exe` on Windows)
2. Run `python restore_sidebar.py --pilot 3` to write 3 test entries
3. Open Claude Desktop and verify those 3 sessions appear in the sidebar
4. Close Claude Desktop again
5. Run `python restore_sidebar.py` for the full restore
6. Open Claude Desktop — all sessions should be back

## Finding the session index folder manually

The script finds this folder automatically in most cases. If it fails (e.g. after an unusual install), here is how to find it yourself.

The folder contains files named `local_<long-random-id>.json` — one per session.

### Windows (installed from the Microsoft Store)

1. Open File Explorer
2. Paste this into the address bar and press Enter:
   ```
   %LOCALAPPDATA%\Packages
   ```
3. Look for a folder starting with `Claude_` (e.g. `Claude_pzs8sxrjxfjjc`)
4. Inside it, navigate to:
   ```
   LocalCache\Roaming\Claude\claude-code-sessions
   ```
5. Open the one subfolder inside, then the one subfolder inside that — you are now in the session index folder. It should contain `local_*.json` files.
6. Copy the full path from the address bar and pass it to `--target`.

### Windows (installed directly, not from the Store)

1. Open File Explorer
2. Paste this into the address bar and press Enter:
   ```
   %APPDATA%\Claude\claude-code-sessions
   ```
3. Open the one subfolder, then the subfolder inside that.
4. Copy the full path and pass it to `--target`.

### macOS

1. Open Finder
2. Press **Cmd+Shift+G** and paste:
   ```
   ~/Library/Application Support/Claude/claude-code-sessions
   ```
3. Open the one subfolder, then the subfolder inside that.
4. Copy the full path and pass it to `--target`.

### Linux

```
~/.config/Claude/claude-code-sessions/<one folder>/<one folder inside that>/
```

## Safe to re-run

Already-indexed sessions are detected and skipped automatically. Re-running is always safe.

## Known limitations

**Session titles show the raw first message, not a clean summary.** Claude Desktop normally generates a short AI summary title after you interact with a session and saves it back to the index file. Since that summary is not stored in the `.jsonl` transcript, the script uses the first message as the title instead. The titles will look messy for sessions that started with a slash command, terminal output, or a long message. They will be replaced automatically with proper summaries the next time you open each session and send a message.

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
