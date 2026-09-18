#!/usr/bin/env python3
"""Claude Code PreToolUse hook that blocks destructive shell commands.

The hook is deliberately dependency-free. Claude Code sends a JSON object on
stdin for every matching Bash tool call; a deny decision is returned on stdout
when a dangerous command is found. All other calls exit quietly with status 0.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import shlex
import sys
from typing import Any, Iterable, TextIO


_SHELL_SEPARATORS = {";", "&&", "||", "|", "&", "\n"}
_SQL_CLIENTS = {
    "duckdb",
    "mariadb",
    "mysql",
    "psql",
    "sqlite",
    "sqlite3",
    "sqlcmd",
}
_SHELL_WRAPPERS = {"bash", "dash", "fish", "ksh", "sh", "zsh"}
_SQL_DROP_RE = re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE)
_SQL_TRUNCATE_RE = re.compile(r"\bTRUNCATE(?:\s+TABLE)?\b", re.IGNORECASE)
_SQL_DELETE_RE = re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE)
_WHERE_RE = re.compile(r"\bWHERE\b", re.IGNORECASE)


def _shell_tokens(command: str) -> list[str]:
    """Return shell words and separators without failing closed on syntax.

    Claude may send an incomplete command while it is being composed. In that
    case a best-effort tokenization is preferable to crashing the hook; the
    regex SQL checks below still provide a safe fallback.
    """

    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|\n")
        lexer.whitespace_split = True
        return list(lexer)
    except (ValueError, TypeError):
        return command.split()


def _segments(tokens: Iterable[str]) -> Iterable[list[str]]:
    segment: list[str] = []
    for token in tokens:
        if token in _SHELL_SEPARATORS:
            if segment:
                yield segment
                segment = []
            continue
        segment.append(token)
    if segment:
        yield segment


def _is_assignment(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token))


def _executable_index(segment: list[str]) -> int:
    """Find the executable after common env/sudo prefixes."""

    index = 0
    while index < len(segment) and _is_assignment(segment[index]):
        index += 1
    if index < len(segment) and segment[index] == "env":
        index += 1
        while index < len(segment) and (_is_assignment(segment[index]) or segment[index] == "-i"):
            index += 1
    if index < len(segment) and segment[index] == "sudo":
        index += 1
        while index < len(segment) and segment[index].startswith("-"):
            index += 1
    return index


def _rm_reason(segment: list[str]) -> str | None:
    index = _executable_index(segment)
    if index >= len(segment) or Path(segment[index]).name != "rm":
        return None
    has_recursive = False
    has_force = False
    for token in segment[index + 1 :]:
        if token == "--":
            break
        if token == "--recursive":
            has_recursive = True
        elif token == "--force":
            has_force = True
        elif token.startswith("-") and not token.startswith("--"):
            flags = token[1:]
            has_recursive |= "r" in flags
            has_force |= "f" in flags
    if has_recursive and has_force:
        return "rm with both recursive and force flags (rm -rf) can erase an entire tree."
    return None


def _git_force_reason(segment: list[str]) -> str | None:
    index = _executable_index(segment)
    if index >= len(segment) or Path(segment[index]).name != "git":
        return None
    tokens = segment[index + 1 :]
    try:
        push_index = tokens.index("push")
    except ValueError:
        return None
    if any(
        token in {"--force", "--force-with-lease", "-f"}
        or token.startswith("--force-with-lease=")
        or token.startswith("--force=")
        for token in tokens[push_index + 1 :]
    ):
        return "a forced git push can rewrite shared history."
    return None


def _sql_reason(segment: list[str]) -> str | None:
    """Detect destructive SQL while allowing ordinary echo/printing commands."""

    if not segment:
        return None
    executable_index = _executable_index(segment)
    # A segment containing only environment assignments (for example
    # ``DEBUG=1``) is valid shell input but has no executable.  Treat it as a
    # harmless no-op instead of allowing the detector itself to raise an
    # IndexError and make the hook noisy.
    if executable_index >= len(segment):
        return None
    executable = Path(segment[executable_index]).name.lower()
    text = " ".join(segment)
    # A literal shown with echo/printf, or a program merely containing SQL in
    # a source string, is not being executed. Cover direct SQL statements and
    # the common command-line SQL clients (including SQL contained in -c args).
    if executable in {"echo", "printf", "print", "cat", "grep", "rg"}:
        return None
    if executable not in _SQL_CLIENTS and executable not in {"drop", "truncate", "delete"}:
        return None
    if _SQL_DROP_RE.search(text):
        return "DROP TABLE is destructive and is blocked by this hook."
    if _SQL_TRUNCATE_RE.search(text):
        return "TRUNCATE is destructive and is blocked by this hook."
    for delete_match in _SQL_DELETE_RE.finditer(text):
        statement_tail = text[delete_match.end() :].split(";", 1)[0]
        if not _WHERE_RE.search(statement_tail):
            return "DELETE FROM without a WHERE clause can remove every row."
    return None


def _wrapped_script(segment: list[str]) -> str | None:
    """Return the inline script from a common ``sh -c`` style wrapper.

    Claude often emits a shell wrapper when it needs a particular shell or
    flags.  The outer command itself is harmless, but the inline script is
    still executed by that shell and must go through the same detector.
    """

    index = _executable_index(segment)
    if index >= len(segment) or Path(segment[index]).name.lower() not in _SHELL_WRAPPERS:
        return None
    args = segment[index + 1 :]
    for position, token in enumerate(args):
        # ``sh -c SCRIPT`` and ``sh -lc SCRIPT`` are the common forms.  Shell
        # options may be combined (for example ``bash -ec SCRIPT``), so look
        # for ``c`` in a short-option cluster as well.  Long options and
        # unrelated operands are left alone to avoid treating their values as
        # executable shell source.
        if token in {"-c", "-lc", "-cl"} and position + 1 < len(args):
            return args[position + 1]
        if token.startswith("-") and not token.startswith("--") and "c" in token[1:]:
            if position + 1 < len(args):
                return args[position + 1]
    return None


def detect_danger(command: str) -> str | None:
    """Return a human-readable block reason, or ``None`` for safe commands."""

    if not isinstance(command, str) or not command.strip():
        return None
    tokens = _shell_tokens(command)
    for segment in _segments(tokens):
        reason = _rm_reason(segment) or _git_force_reason(segment) or _sql_reason(segment)
        if reason:
            return reason
        # Recursively inspect inline shell scripts such as
        # ``bash -lc 'git push --force origin main'``.  The depth is naturally
        # bounded by the command's token count, and an empty script is safe.
        wrapped = _wrapped_script(segment)
        if wrapped:
            reason = detect_danger(wrapped)
            if reason:
                return reason
    return None


def _command_from_payload(payload: dict[str, Any]) -> str | None:
    if payload.get("tool_name") not in {None, "Bash"}:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command", tool_input.get("cmd"))
    return command if isinstance(command, str) else None


def _hooks_dir() -> Path:
    return Path(os.environ.get("CLAUDE_HOOKS_DIR", str(Path.home() / ".claude" / "hooks"))).expanduser()


def _log_block(payload: dict[str, Any], command: str, reason: str) -> None:
    hooks_dir = _hooks_dir()
    log_path = Path(os.environ.get("CLAUDE_HOOK_LOG", str(hooks_dir / "blocked.log"))).expanduser()
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "attempted_command": command,
        "project_path": payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd(),
        "reason": reason,
    }
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        # A logging failure must not allow a destructive operation through,
        # and must not make Claude's hook invocation fail noisily.
        pass


def _write_deny(stdout: TextIO, reason: str) -> None:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Blocked by destructive-command-guard: {reason} "
                "The command was not run; review it and use a narrower, reversible operation."
            ),
        }
    }
    json.dump(output, stdout, ensure_ascii=False)
    stdout.write("\n")


def main(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
    try:
        payload = json.load(stdin)
    except (json.JSONDecodeError, TypeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0
    command = _command_from_payload(payload)
    reason = detect_danger(command or "")
    if reason:
        _log_block(payload, command or "", reason)
        _write_deny(stdout, reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
