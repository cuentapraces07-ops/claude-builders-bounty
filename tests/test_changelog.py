from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.changelog import classify, commits_since, latest_tag, main, markdown


class ChangelogTests(unittest.TestCase):
    def test_classifies_conventional_commits_and_keywords(self) -> None:
        self.assertEqual(classify("feat: add export command")[0], "Added")
        self.assertEqual(classify("fix(parser): handle an empty tag")[0], "Fixed")
        self.assertEqual(classify("remove legacy endpoint")[0], "Removed")
        self.assertEqual(classify("docs: update examples")[0], "Changed")

    def test_reads_commits_since_last_tag_from_a_real_git_repo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            run = lambda *args: subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
            run("init", "-q")
            run("config", "user.name", "Test Author")
            run("config", "user.email", "test@example.invalid")
            (repo / "notes.txt").write_text("initial\n", encoding="utf-8")
            run("add", "notes.txt")
            run("commit", "-qm", "feat: add notes")
            run("tag", "v1.0.0")
            (repo / "notes.txt").write_text("fixed\n", encoding="utf-8")
            run("commit", "-qam", "fix: correct note output")
            commits = commits_since(repo, "v1.0.0")
            self.assertEqual(len(commits), 1)
            output = markdown(repo, commits, "v1.0.0", "2026-09-18")
            self.assertIn("### Fixed", output)
            self.assertIn("correct note output", output)
            self.assertNotIn("feat: add notes", output)

    def test_default_includes_full_history_when_repository_has_no_tags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            run = lambda *args: subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
            run("init", "-q")
            run("config", "user.name", "Test Author")
            run("config", "user.email", "test@example.invalid")
            (repo / "notes.txt").write_text("initial\n", encoding="utf-8")
            run("add", "notes.txt")
            run("commit", "-qm", "feat: add notes")
            (repo / "notes.txt").write_text("updated\n", encoding="utf-8")
            run("commit", "-qam", "fix: correct note output")

            self.assertIsNone(latest_tag(repo))
            commits = commits_since(repo, None)
            self.assertEqual([commit.subject for commit in commits], ["feat: add notes", "fix: correct note output"])
            output = markdown(repo, commits, None, "2026-09-22")
            self.assertIn("### Added", output)
            self.assertIn("### Fixed", output)

    def test_empty_range_is_explicit_and_cli_stdout_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            run = lambda *args: subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
            run("init", "-q")
            run("config", "user.name", "Test Author")
            run("config", "user.email", "test@example.invalid")
            (repo / "notes.txt").write_text("initial\n", encoding="utf-8")
            run("add", "notes.txt")
            run("commit", "-qm", "docs: add notes")
            run("tag", "v1.0.0")

            generated = markdown(repo, commits_since(repo, "v1.0.0"), "v1.0.0", "2026-09-21")
            self.assertIn("No changes since the selected baseline.", generated)
            self.assertEqual(main(["--repo", str(repo), "--base", "v1.0.0", "--date", "2026-09-21", "--stdout"]), 0)


if __name__ == "__main__":
    unittest.main()
