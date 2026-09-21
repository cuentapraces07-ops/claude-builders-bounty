from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from hooks.destructive_command_guard import detect_danger, main
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


if __name__ == "__main__":
    unittest.main()
