"""Structural acceptance checks for the greenfield CLAUDE.md template.

These tests intentionally verify only the written contract.  They do not claim
to exercise a live Claude Code session, which requires a separately configured
authenticated installation.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "CLAUDE.md"


class ClaudeTemplateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_required_stack_and_sections_are_explicit(self) -> None:
        for value in (
            "Next.js 15 App Router",
            "better-sqlite3",
            "Turso/libSQL",
            "## Project structure",
            "## Naming conventions",
            "## Database and migration rules",
            "## Components, routes, and Server Actions",
            "## What we do not do (and why)",
            "## Greenfield verification protocol",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.text)

    def test_actions_and_anti_patterns_include_reasoning(self) -> None:
        for value in (
            "**Why:** limiting the client boundary",
            "**Why:** one validated representation",
            "**Why:** a caller can bypass the UI",
            "**Why:** a narrow data boundary",
            "| Avoid | Reason |",
            "No floating-point money",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.text)

    def test_greenfield_defaults_and_pre_pr_gate_are_actionable(self) -> None:
        for value in (
            "pnpm lint",
            "pnpm typecheck",
            "pnpm test -- --coverage",
            "pnpm build",
            "pnpm test:e2e --project=chromium",
            "without asking the owner to choose among those settled defaults",
            "does **not** claim that a live Claude Code session has been run",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.text)


if __name__ == "__main__":
    unittest.main()
