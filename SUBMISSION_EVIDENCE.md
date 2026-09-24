# Bounty #3 submission evidence

This is a local review aid for the destructive-command PreToolUse hook. It is
not an Opire claim, pull request, or payment request.

## Acceptance criteria mapping

- **Claude Code hook format:** `hooks/install.py` installs the hook under
  `~/.claude/hooks/` and merges the Bash matcher into existing settings.
- **Required destructive patterns:** the guard blocks recursive/forced `rm`,
  `git push --force` variants, `DROP TABLE`, `TRUNCATE`, and `DELETE FROM`
  unless the same SQL statement has a `WHERE` clause.
- **Nested and wrapped commands:** it inspects common shell wrappers,
  substitutions, `eval`, `find -exec`, `xargs`, and command-prefix utilities
  such as `time`, `nice`, `timeout`, and `stdbuf`, with a finite nesting bound.
- **Audit record:** each denial records a UTC timestamp, redacted and
  length-limited command, project path, and reason in
  `~/.claude/hooks/blocked.log`.
- **Clear denial:** the PreToolUse response denies the command and gives Claude
  a reason and safer alternative. Invalid hook input and log-write failure
  fail closed.
- **Benign commands:** dedicated tests cover ordinary commands, scoped SQL
  deletes, and literal or escaped examples.
- **Installation docs:** the root README documents installation with one
  command: `python3 hooks/install.py`.

## Verification

Run from the repository root:

```text
python -m unittest discover -s tests -v
python -m pytest -q
python -m compileall -q hooks tests
```

On 2026-09-24, Windows unittest discovery ran **35 test methods** (32 passed,
3 platform-specific tests skipped); pytest reported **32 passed, 3 skipped, and
61 subtests passed**. `git diff --check` completed without errors. The tests
use temporary settings and logs and do not modify the user's Claude Code
configuration. POSIX permission and symlink checks require a POSIX run.

## Scope and limitation

The hook is a best-effort command guard, not a complete Bash parser or a
security sandbox. The README documents syntax that can evade heuristic
inspection and false-positive risks; ambiguous or over-nested inputs are
handled conservatively.

No public claim, push, PR, or payment action has been made.
