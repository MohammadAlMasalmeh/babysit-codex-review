import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "codex_review.py"
SPEC = importlib.util.spec_from_file_location("codex_review", SCRIPT)
codex_review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(codex_review)

HEAD = "0f1489d1bd9302efa93b1961ec5a6e57759d3e1a"
SINCE = "2026-09-03T20:12:53Z"


def empty_results():
    return {
        "issue_comments": [],
        "review_comments": [],
        "reviews": [],
        "reactions": [],
    }


class ClassifyCodexReviewTest(unittest.TestCase):
    def test_accepts_clean_comment_for_current_head(self):
        results = empty_results()
        results["issue_comments"].append(
            {
                "user": {"login": "chatgpt-codex-connector[bot]"},
                "created_at": "2026-09-03T20:18:23Z",
                "body": (
                    "Codex Review: Didn't find any major issues. Chef's kiss.\n\n"
                    "**Reviewed commit:** `0f1489d1bd`"
                ),
                "html_url": "https://github.com/example/repo/pull/1#issuecomment-1",
            }
        )

        outcome = codex_review.classify(results, HEAD, SINCE)

        self.assertEqual(outcome["status"], "clean")
        self.assertEqual(outcome["reviewed_commit"], "0f1489d1bd")

    def test_ignores_clean_comment_for_stale_head(self):
        results = empty_results()
        results["issue_comments"].append(
            {
                "user": {"login": "chatgpt-codex-connector[bot]"},
                "created_at": "2026-09-03T20:18:23Z",
                "body": (
                    "Codex Review: Didn't find any major issues. Nice work!\n\n"
                    "**Reviewed commit:** `de390a7f30`"
                ),
            }
        )

        self.assertIsNone(codex_review.classify(results, HEAD, SINCE))

    def test_returns_inline_findings_before_clean_signals(self):
        results = empty_results()
        results["reviews"].append(
            {
                "id": 987,
                "user": {"login": "chatgpt-codex-connector[bot]"},
                "submitted_at": "2026-09-03T20:13:30Z",
                "commit_id": HEAD,
            }
        )
        results["review_comments"].append(
            {
                "id": 3928174211,
                "user": {"login": "chatgpt-codex-connector[bot]"},
                "created_at": "2026-09-03T20:13:30Z",
                "commit_id": HEAD,
                "pull_request_review_id": 987,
                "path": "utils/tax.ts",
                "line": 42,
                "body": "Apply the 30-day floor here.",
                "html_url": "https://github.com/example/repo/pull/1#discussion_r1",
            }
        )
        results["reactions"].append(
            {
                "user": {"login": "chatgpt-codex-connector[bot]"},
                "created_at": "2026-09-03T20:13:31Z",
                "content": "+1",
            }
        )

        outcome = codex_review.classify(results, HEAD, SINCE)

        self.assertEqual(outcome["status"], "findings")
        self.assertEqual(outcome["findings"][0]["id"], 3928174211)

    def test_accepts_codex_thumbs_up(self):
        results = empty_results()
        results["reactions"].append(
            {
                "user": {"login": "chatgpt-codex-connector[bot]"},
                "created_at": "2026-09-03T20:13:31Z",
                "content": "+1",
            }
        )

        outcome = codex_review.classify(results, HEAD, SINCE)

        self.assertEqual(outcome["status"], "clean")
        self.assertEqual(outcome["signal"], "thumbs_up")

    def test_rejects_spoofed_bot_and_qualified_clean_text(self):
        for login, body in (
            (
                "chatgpt-codex-connector-attacker",
                "Codex Review: Didn't find any major issues.",
            ),
            (
                "chatgpt-codex-connector[bot]",
                "Codex Review: No major issues, but one correctness concern remains.",
            ),
        ):
            with self.subTest(login=login, body=body):
                results = empty_results()
                results["issue_comments"].append(
                    {
                        "user": {"login": login},
                        "created_at": "2026-09-03T20:18:23Z",
                        "body": body + "\n\n**Reviewed commit:** `0f1489d1bd`",
                    }
                )
                self.assertIsNone(codex_review.classify(results, HEAD, SINCE))

    def test_surfaces_connector_failure(self):
        results = empty_results()
        results["issue_comments"].append(
            {
                "user": {"login": "chatgpt-codex-connector[bot]"},
                "created_at": "2026-09-03T20:18:23Z",
                "body": "Codex is unable to review this repository because it is not enabled.",
                "html_url": "https://github.com/example/repo/pull/1#issuecomment-2",
            }
        )

        outcome = codex_review.classify(results, HEAD, SINCE)

        self.assertEqual(outcome["status"], "error")


if __name__ == "__main__":
    unittest.main()
