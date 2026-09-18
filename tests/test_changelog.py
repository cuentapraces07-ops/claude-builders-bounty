from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.changelog import classify, commits_since, markdown


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


if __name__ == "__main__":
    unittest.main()
