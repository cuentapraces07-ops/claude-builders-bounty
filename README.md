# Claude Builders Bounty 🤖

> A community bounty board for Claude Code builders.

Building with Claude Code? Have tasks to delegate?
Want to get paid for contributing to AI projects?
You're in the right place.

---

## How it works

**To post a bounty**
1. Open a GitHub issue with a clear description and acceptance criteria
2. Comment `/opire create $XXX` in the issue to set the reward
3. Share the link — contributors will find it

**To claim a bounty**
1. Browse the open issues below
2. Comment `/opire try` in the issue you want to work on
3. Submit a PR — payment is automatic on merge ✅

---

## Active Bounties

| # | Task | Amount | Status |
|---|------|--------|--------|
| [#1](../../issues/1) | SKILL: Generate a CHANGELOG from git history | $50 | 🟢 Open |
| [#2](../../issues/2) | TEMPLATE: CLAUDE.md for a Next.js + SQLite project | $75 | 🟢 Open |
| [#3](../../issues/3) | HOOK: Block destructive bash commands in Claude Code | $100 | 🟢 Open |
| [#4](../../issues/4) | AGENT: PR reviewer with structured Markdown output | $150 | 🟢 Open |
| [#5](../../issues/5) | WORKFLOW: n8n + Claude API — automated weekly dev summary | $200 | 🟢 Open |

---

## Rules

- Tasks must be related to Claude Code or AI tooling
- Every issue must have clear acceptance criteria before a bounty is activated
- Payment is handled by [Opire](https://opire.dev) (Stripe)
- Quality over speed — a solid PR beats a fast one

## Destructive-command guard hook

This repository includes `hooks/destructive_command_guard.py`, a dependency-free
Claude Code `PreToolUse` hook for the bounty in [issue #3](../../issues/3). It
denies `rm -rf`, `git push --force`, `DROP TABLE`, `TRUNCATE`, and `DELETE FROM`
without a `WHERE` clause. Every denial is appended as one JSON line to
`~/.claude/hooks/blocked.log`, including the UTC timestamp, attempted command,
and project path. Ordinary commands (including scoped SQL deletes) remain
untouched. The denial response contains a clear explanation for Claude and a
safer, scoped alternative (for example, previewing files before removal,
pushing a new branch, or adding a reviewed SQL predicate).

From the repository root, install it and merge its `PreToolUse` matcher into
your existing Claude settings with one command:

```bash
python3 hooks/install.py
```

The installer copies the hook to `~/.claude/hooks/` and preserves unrelated
settings. To configure it manually instead, add this matcher to
`~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {"type": "command", "command": "python3 ~/.claude/hooks/destructive_command_guard.py"}
        ]
      }
    ]
  }
}
```

---

## Community

- 🐦 X: [@ClaudeBounty](https://x.com/ClaudeBounty)
- 📧 Contact: claudebounty@gmail.com

---

*Started by the Claude builder community · March 2026 · MIT License*
