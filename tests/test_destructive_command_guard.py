from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from hooks.destructive_command_guard import _redact_command_for_log, detect_danger, main
from hooks.install import install


class GuardDetectionTests(unittest.TestCase):
    def test_blocks_short_rm_rf_in_shell_chain(self) -> None:
        self.assertIn("rm -rf", detect_danger("printf 'review'; rm -rf ./build"))

    def test_blocks_long_rm_flags_in_any_order(self) -> None:
        self.assertIsNotNone(detect_danger("rm --force --recursive ./tmp"))

    def test_blocks_force_push(self) -> None:
        self.assertIsNotNone(detect_danger("git -C repo push origin main --force"))
        self.assertIsNotNone(detect_danger("git push --force-with-lease origin main"))
        self.assertIsNotNone(detect_danger("git push --force-with-lease=main origin main"))

    def test_blocks_dangerous_commands_inside_shell_wrappers(self) -> None:
        self.assertIsNotNone(detect_danger("bash -lc 'rm -rf ./build'"))
        self.assertIsNotNone(detect_danger("bash -ec 'rm -rf ./build'"))
        self.assertIsNotNone(detect_danger("sh -uc 'git push --force origin main'"))
        self.assertIsNotNone(detect_danger("sh -c 'git push --force origin main'"))
        self.assertIsNotNone(detect_danger("zsh -c 'DELETE FROM accounts'"))

    def test_blocks_dangerous_commands_inside_shell_substitutions(self) -> None:
        for command in (
            'echo "$(rm -rf ./build)"',
            "target=$(git push --force origin main)",
            "echo `rm -rf ./build`",
            "cat <(psql -c 'DELETE FROM accounts')",
            "cat >(sqlite3 db.sqlite 'DROP TABLE users')",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(detect_danger(command))

    def test_allows_quoted_or_escaped_substitution_examples(self) -> None:
        for command in (
            "echo '$(rm -rf ./build)'",
            'echo "\\$(rm -rf ./build)"',
            "echo '`git push --force origin main`'",
            'echo "literal rm -rf ./build"',
        ):
            with self.subTest(command=command):
                self.assertIsNone(detect_danger(command))

    def test_excessive_shell_nesting_is_blocked_without_recursing_unboundedly(self) -> None:
        command = "echo " + "$(" * 40 + "rm -rf ./build" + ")" * 40
        self.assertIn("inspection limit", detect_danger(command))

    def test_blocks_destructive_sql(self) -> None:
        self.assertIsNotNone(detect_danger("DROP TABLE accounts"))
        self.assertIsNotNone(detect_danger("TRUNCATE TABLE accounts"))
        self.assertIsNotNone(detect_danger("DELETE FROM accounts"))
        self.assertIsNotNone(detect_danger("psql -c 'DROP TABLE accounts'"))

    def test_allows_scoped_delete(self) -> None:
        self.assertIsNone(detect_danger("DELETE FROM accounts WHERE id = 7"))

    def test_blocks_unscoped_delete_before_a_later_where_clause(self) -> None:
        command = "psql -c 'DELETE FROM accounts; SELECT * FROM audit WHERE id = 7'"
        self.assertIsNotNone(detect_danger(command))

    def test_allows_normal_commands_and_literal_output(self) -> None:
        for command in (
            "git status",
            "rm -r ./build",
            "DEBUG=1",
            "echo 'DROP TABLE accounts'",
            "python -c \"print('DROP TABLE accounts')\"",
            "bash -lc \"echo 'rm -rf ./build'\"",
            "bash -e 'echo safe'",
            "sh -c 'echo DELETE FROM accounts'",
            "npm test",
        ):
            with self.subTest(command=command):
                self.assertIsNone(detect_danger(command))


class HookInvocationTests(unittest.TestCase):
    def test_denies_and_logs_blocked_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            payload = {
                "tool_name": "Bash",
                "tool_input": {"command": "git push --force origin main"},
                "cwd": "/workspace/example",
            }
            with mock.patch.dict(
                "os.environ",
                {"CLAUDE_HOOKS_DIR": directory},
                clear=False,
            ):
                exit_code = main(io.StringIO(json.dumps(payload)), output)
            self.assertEqual(exit_code, 0)
            decision = json.loads(output.getvalue())
            self.assertEqual(decision["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertIn("forced git push", decision["hookSpecificOutput"]["permissionDecisionReason"])
            self.assertIn("Safe alternative", decision["hookSpecificOutput"]["permissionDecisionReason"])
            self.assertIn("new branch", decision["hookSpecificOutput"]["permissionDecisionReason"])
            record = json.loads((Path(directory) / "blocked.log").read_text(encoding="utf-8").strip())
            self.assertEqual(record["attempted_command"], "git push --force origin main")
            self.assertEqual(record["project_path"], "/workspace/example")
            self.assertIn("timestamp", record)

    def test_pretooluse_denies_nested_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            payload = {
                "tool_name": "Bash",
                "tool_input": {"command": 'echo "$(rm -rf ./build)"'},
            }
            with mock.patch.dict("os.environ", {"CLAUDE_HOOKS_DIR": directory}, clear=False):
                self.assertEqual(main(io.StringIO(json.dumps(payload)), output), 0)
            decision = json.loads(output.getvalue())
            self.assertEqual(decision["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_redacts_credentials_before_persisting_blocked_command(self) -> None:
        command = (
            "git push --force origin main --token cli-secret "
            '--api-key="key with spaces" PASSWORD=env-secret '
            'Authorization: "basic header-secret" '
            "-H 'X-Trace: Bearer bearer-secret' "
            "https://build-user:url-secret@example.test/repo "
            "github_pat_0123456789abcdefghijklmnop"
        )
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            payload = {"tool_name": "Bash", "tool_input": {"command": command}}
            with mock.patch.dict("os.environ", {"CLAUDE_HOOKS_DIR": directory}, clear=False):
                self.assertEqual(main(io.StringIO(json.dumps(payload)), output), 0)

            decision = json.loads(output.getvalue())
            self.assertEqual(decision["hookSpecificOutput"]["permissionDecision"], "deny")
            log_text = (Path(directory) / "blocked.log").read_text(encoding="utf-8")
            for secret in (
                "cli-secret",
                "key with spaces",
                "env-secret",
                "basic header-secret",
                "bearer-secret",
                "build-user:url-secret",
                "github_pat_0123456789abcdefghijklmnop",
            ):
                with self.subTest(secret=secret):
                    self.assertNotIn(secret, log_text)
            record = json.loads(log_text.strip())
            self.assertIn("--token [REDACTED]", record["attempted_command"])
            self.assertIn('--api-key="[REDACTED]"', record["attempted_command"])
            self.assertIn("PASSWORD=[REDACTED]", record["attempted_command"])
            self.assertIn('X-Trace: Bearer [REDACTED]', record["attempted_command"])
            self.assertIn("https://[REDACTED]@example.test", record["attempted_command"])

    def test_truncates_oversized_commands_in_the_audit_log(self) -> None:
        logged = _redact_command_for_log("rm -rf ./build " + "x" * 5000)
        self.assertLessEqual(len(logged), 4014)
        self.assertTrue(logged.endswith("…[TRUNCATED]"))

    def test_safe_command_is_silent(self) -> None:
        output = io.StringIO()
        payload = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
        self.assertEqual(main(io.StringIO(json.dumps(payload)), output), 0)
        self.assertEqual(output.getvalue(), "")

    def test_cmd_alias_uses_the_same_pretooluse_wire_format(self) -> None:
        output = io.StringIO()
        payload = {"tool_name": "Bash", "tool_input": {"cmd": "rm -rf ./build"}}
        self.assertEqual(main(io.StringIO(json.dumps(payload)), output), 0)
        decision = json.loads(output.getvalue())
        self.assertEqual(decision["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(decision["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_logging_failure_still_denies_the_command(self) -> None:
        output = io.StringIO()
        payload = {"tool_name": "Bash", "tool_input": {"command": "DROP TABLE accounts"}}
        with mock.patch.object(Path, "open", side_effect=OSError("disk full")):
            self.assertEqual(main(io.StringIO(json.dumps(payload)), output), 0)
        decision = json.loads(output.getvalue())
        self.assertEqual(decision["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("DROP TABLE", decision["hookSpecificOutput"]["permissionDecisionReason"])

    def test_non_bash_tool_is_ignored(self) -> None:
        output = io.StringIO()
        payload = {"tool_name": "Read", "tool_input": {"command": "rm -rf /"}}
        self.assertEqual(main(io.StringIO(json.dumps(payload)), output), 0)
        self.assertEqual(output.getvalue(), "")


class InstallerTests(unittest.TestCase):
    def test_installer_preserves_existing_hooks_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            settings_path = home / ".claude" / "settings.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                json.dumps({"hooks": {"PreToolUse": [{"matcher": "Read", "hooks": []}]}}),
                encoding="utf-8",
            )
            install(home)
            install(home)
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(len(settings["hooks"]["PreToolUse"]), 2)
            self.assertTrue((home / ".claude" / "hooks" / "destructive_command_guard.py").exists())

    def test_installed_hook_processes_real_pretooluse_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            installed = install(home)
            payload = {
                "tool_name": "Bash",
                "tool_input": {"command": 'echo "$(rm -rf ./build)"'},
                "cwd": str(home),
            }
            environment = os.environ.copy()
            environment["CLAUDE_HOOKS_DIR"] = str(installed.parent)
            result = subprocess.run(
                [sys.executable, str(installed)],
                input=json.dumps(payload),
                capture_output=True,
                check=False,
                env=environment,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            decision = json.loads(result.stdout)
            self.assertEqual(decision["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertTrue((installed.parent / "blocked.log").is_file())


if __name__ == "__main__":
    unittest.main()
