from __future__ import annotations

import io
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from scripts.changelog import classify, commits_since, latest_tag, main, markdown


class ChangelogTests(unittest.TestCase):
    def test_project_skill_exposes_slash_command_and_uses_existing_generator(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        skill_path = repo / ".claude" / "skills" / "generate-changelog" / "SKILL.md"
        skill = skill_path.read_text(encoding="utf-8")
        readme = (repo / "README.md").read_text(encoding="utf-8")

        self.assertTrue(skill.startswith("---\nname: generate-changelog\n"))
        self.assertIn("bash changelog.sh --stdout", skill)
        self.assertIn("bash changelog.sh`", skill)
        self.assertIn("/generate-changelog", readme)

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

    def test_default_ignores_tags_not_merged_into_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            run = lambda *args: subprocess.run(
                ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
            )
            run("init", "-q")
            run("config", "user.name", "Test Author")
            run("config", "user.email", "test@example.invalid")
            (repo / "notes.txt").write_text("initial\n", encoding="utf-8")
            run("add", "notes.txt")
            run("commit", "-qm", "feat: add notes")
            run("branch", "-M", "main")
            run("tag", "v1.0.0")
            (repo / "notes.txt").write_text("main update\n", encoding="utf-8")
            run("commit", "-qam", "fix: update main notes")

            run("checkout", "-qb", "unmerged-release")
            (repo / "notes.txt").write_text("unmerged release\n", encoding="utf-8")
            run("commit", "-qam", "feat: add unmerged release")
            run("tag", "v99.0.0")
            run("checkout", "-q", "main")

            self.assertEqual(latest_tag(repo), "v1.0.0")
            commits = commits_since(repo, latest_tag(repo))
            self.assertEqual([commit.subject for commit in commits], ["fix: update main notes"])

    def test_markdown_escapes_untrusted_commit_subjects_and_authors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            run = lambda *args: subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
            run("init", "-q")
            run("config", "user.name", "Reviewer ](javascript:alert(1))")
            run("config", "user.email", "test@example.invalid")
            (repo / "notes.txt").write_text("content\n", encoding="utf-8")
            run("add", "notes.txt")
            run("commit", "-qm", "feat: add [click](javascript:alert(1)) <img src=x onerror=alert(1)>")

            output = markdown(repo, commits_since(repo, None), None, "2026-09-22")

        self.assertNotIn("](javascript:", output)
        self.assertNotIn(" <img", output)
        self.assertIn(r"\[click\]", output)
        self.assertIn(r"\<img", output)
        self.assertIn(r"Reviewer \]\(javascript:alert\(1\)\)", output)

    def test_generation_date_rejects_invalid_or_markdown_injection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            for bad_date in ("2026-02-30", "2026-09-22\n## Injected", "<script>alert(1)</script>"):
                with self.subTest(bad_date=bad_date):
                    with self.assertRaisesRegex(ValueError, "valid YYYY-MM-DD"):
                        markdown(repo, [], None, bad_date)

    def test_cli_reports_invalid_date_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            run = lambda *args: subprocess.run(
                ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
            )
            run("init", "-q")
            run("config", "user.name", "Test Author")
            run("config", "user.email", "test@example.invalid")
            (repo / "notes.txt").write_text("initial\n", encoding="utf-8")
            run("add", "notes.txt")
            run("commit", "-qm", "docs: add notes")

            errors = io.StringIO()
            with redirect_stderr(errors):
                result = main(["--repo", str(repo), "--date", "2026-02-30", "--stdout"])

        self.assertEqual(result, 2)
        self.assertIn("changelog: date must be a valid YYYY-MM-DD value", errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())

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
