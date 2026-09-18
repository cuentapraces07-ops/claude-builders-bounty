import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from claude_review import (
    PullRequest,
    _parse_claude_response,
    changed_files,
    diff_stats,
    heuristic_review,
    parse_pull_url,
    render,
)


class ReviewTests(unittest.TestCase):
    def test_parse_pull_url(self):
        self.assertEqual(parse_pull_url("https://github.com/a-b/repo_1/pull/42"), ("a-b", "repo_1", 42))

    def test_rejects_non_github_url(self):
        with self.assertRaises(ValueError):
            parse_pull_url("http://github.com/a/repo/pull/1")

    def test_diff_stats_and_risk_detection(self):
        diff = """diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n+eval(user_input)\n+print('safe')\n- old\n"""
        pr = PullRequest("https://github.com/a/r/pull/1", "a", "r", 1, "Example", "", diff)
        self.assertEqual(diff_stats(diff), (1, 2, 1))
        result = heuristic_review(pr)
        self.assertTrue(any("eval" in risk.lower() for risk in result.risks))
        self.assertIn("## Confidence:", render(pr, result))

    def test_diff_stats_counts_deleted_files(self):
        diff = """diff --git a/removed.py b/removed.py
--- a/removed.py
+++ /dev/null
@@ -1 +0,0 @@
-old()
"""
        self.assertEqual(changed_files(diff), ("removed.py",))
        self.assertEqual(diff_stats(diff), (1, 0, 1))

    def test_safe_review_still_has_actionable_suggestion(self):
        pr = PullRequest("https://github.com/a/r/pull/2", "a", "r", 2, "Docs", "", "")
        result = heuristic_review(pr)
        self.assertTrue(result.suggestions)
        self.assertEqual(result.confidence, "Low")
        self.assertGreaterEqual(result.summary.count("."), 2)

    def test_claude_response_validation(self):
        valid = {
            "content": [
                {
                    "text": '{"summary":"One. Two.","risks":[],"suggestions":["Test"],"confidence":"High"}'
                }
            ]
        }
        result = _parse_claude_response(valid)
        self.assertEqual(result.confidence, "High")
        self.assertEqual(result.suggestions, ("Test",))

        with self.assertRaises(RuntimeError):
            _parse_claude_response({"content": []})
        with self.assertRaises(RuntimeError):
            _parse_claude_response({"content": [{"text": '{"summary":"ok","risks":"not-list"}'}]})


if __name__ == "__main__":
    unittest.main()
