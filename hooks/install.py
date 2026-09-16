#!/usr/bin/env python3
"""Install the destructive-command hook without overwriting other settings."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parent
HOOK_NAME = "destructive_command_guard.py"
HOOK_COMMAND = f"python3 ~/.claude/hooks/{HOOK_NAME}"


def _hook_entry() -> dict[str, str]:
    return {"type": "command", "command": HOOK_COMMAND}


def install(home: Path | None = None) -> Path:
    home = home or Path.home()
    hooks_dir = home / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    destination = hooks_dir / HOOK_NAME
    shutil.copy2(ROOT / HOOK_NAME, destination)
    destination.chmod(destination.stat().st_mode | 0o111)

    settings_path = home / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Cannot read {settings_path}: {exc}") from exc
        if not isinstance(settings, dict):
            raise RuntimeError(f"Expected a JSON object in {settings_path}")
    else:
        settings = {}
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise RuntimeError("The existing hooks setting is not a JSON object")
    pre_tool_use = hooks.setdefault("PreToolUse", [])
    if not isinstance(pre_tool_use, list):
        raise RuntimeError("The existing PreToolUse setting is not a JSON array")
    for matcher in pre_tool_use:
        if not isinstance(matcher, dict):
            continue
        nested = matcher.get("hooks", [])
        if isinstance(nested, list) and any(
            isinstance(entry, dict) and entry.get("command") == HOOK_COMMAND for entry in nested
        ):
            break
    else:
        pre_tool_use.append({"matcher": "Bash", "hooks": [_hook_entry()]})
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return destination


if __name__ == "__main__":
    try:
        installed = install()
    except (OSError, RuntimeError) as exc:
        print(f"Installation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Installed {installed} and updated ~/.claude/settings.json")
