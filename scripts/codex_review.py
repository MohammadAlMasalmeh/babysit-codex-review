#!/usr/bin/env python3
"""Request a GitHub Codex review and wait for the result."""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


BOT_LOGINS = (
    "chatgpt-codex-connector",
    "chatgpt-codex-connector[bot]",
)
CLEAN_OPENING = re.compile(
    r"^codex review:\s*(?:didn't find any major issues|"
    r"did not find any major issues|no major issues(?: found)?)"
    r"(?:[.!]\s*(?:chef'?s kiss|nice work)[.!]?)?[.!]?$",
    re.I,
)
FAILURE_PHRASES = (
    "unable to review",
    "cannot review",
    "can't review",
    "review failed",
    "quota",
    "not enabled",
)


class CommandError(RuntimeError):
    pass


def run(command: List[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise CommandError("{}: {}".format(" ".join(command), detail))
    return result.stdout


def gh_json(args: List[str]) -> Any:
    output = run(["gh"] + args)
    return json.loads(output) if output.strip() else None


def gh_json_paginated(args: List[str]) -> List[Any]:
    output = run(["gh"] + args + ["--paginate", "--slurp"])
    pages = json.loads(output) if output.strip() else []
    return [item for page in pages for item in page]


def is_bot(login: Optional[str]) -> bool:
    return login in BOT_LOGINS


def parse_reviewed_commit(body: str) -> Optional[str]:
    match = re.search(r"\*\*Reviewed commit:\*\*\s*`([0-9a-f]{7,40})`", body, re.I)
    return match.group(1).lower() if match else None


def sha_matches(reviewed: Optional[str], head: str) -> bool:
    if not reviewed:
        return False
    reviewed = reviewed.lower()
    head = head.lower()
    return head.startswith(reviewed) or reviewed.startswith(head)


def is_clean_body(body: str) -> bool:
    first_line = body.replace("’", "'").splitlines()[0].strip() if body else ""
    return bool(CLEAN_OPENING.search(first_line))


def resolve_repo(repo: Optional[str]) -> str:
    if repo:
        return repo
    data = gh_json(["repo", "view", "--json", "nameWithOwner"])
    return data["nameWithOwner"]


def resolve_pr(repo: str, pr: Optional[int]) -> Dict[str, Any]:
    command = ["pr", "view"]
    if pr is not None:
        command.append(str(pr))
    command += ["--repo", repo, "--json", "number,headRefOid,state,url"]
    data = gh_json(command)
    if data["state"] != "OPEN":
        raise CommandError("PR #{} is {}, not OPEN".format(data["number"], data["state"]))
    return data


def api(
    repo: str,
    endpoint: str,
    fields: Optional[Dict[str, str]] = None,
    paginate: bool = False,
) -> Any:
    args = ["api", "repos/{}/{}".format(repo, endpoint)]
    if fields:
        args += ["--method", "POST"]
        for key, value in fields.items():
            args += ["-f", "{}={}".format(key, value)]
    return gh_json_paginated(args) if paginate else gh_json(args)


def request_review(repo: str, pr: int) -> Dict[str, Any]:
    return api(repo, "issues/{}/comments".format(pr), {"body": "@codex review"})


def get_results(
    repo: str, pr: int, since: str, request_comment_id: Optional[int]
) -> Dict[str, Any]:
    issue_comments = api(
        repo,
        "issues/{}/comments?since={}&per_page=100".format(pr, since),
        paginate=True,
    )
    review_comments = api(
        repo,
        "pulls/{}/comments?since={}&per_page=100".format(pr, since),
        paginate=True,
    )
    reviews = api(
        repo,
        "pulls/{}/reviews?per_page=100".format(pr),
        paginate=True,
    )
    reactions = (
        api(
            repo,
            "issues/comments/{}/reactions?per_page=100".format(request_comment_id),
            paginate=True,
        )
        if request_comment_id
        else []
    )
    return {
        "issue_comments": issue_comments or [],
        "review_comments": review_comments or [],
        "reviews": reviews or [],
        "reactions": reactions or [],
    }


def after_since(value: Optional[str], since: str) -> bool:
    return bool(value and value >= since)


def one_second_before(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed - timedelta(seconds=1)).astimezone(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def classify(results: Dict[str, Any], head: str, since: str) -> Optional[Dict[str, Any]]:
    completed_review_ids = {
        review.get("id")
        for review in results["reviews"]
        if is_bot((review.get("user") or {}).get("login"))
        and after_since(review.get("submitted_at"), since)
        and sha_matches(review.get("commit_id"), head)
    }
    findings = []
    for comment in results["review_comments"]:
        user = (comment.get("user") or {}).get("login")
        if not is_bot(user) or not after_since(comment.get("created_at"), since):
            continue
        if comment.get("pull_request_review_id") not in completed_review_ids:
            continue
        commit = comment.get("commit_id")
        if commit and not sha_matches(commit, head):
            continue
        findings.append(
            {
                "id": comment.get("id"),
                "body": comment.get("body", ""),
                "commit": commit,
                "line": comment.get("line") or comment.get("original_line"),
                "path": comment.get("path"),
                "url": comment.get("html_url"),
            }
        )

    if findings:
        return {"status": "findings", "head": head, "findings": findings}

    for comment in results["issue_comments"]:
        user = (comment.get("user") or {}).get("login")
        body = comment.get("body", "")
        if not is_bot(user) or not after_since(comment.get("created_at"), since):
            continue
        reviewed = parse_reviewed_commit(body)
        if is_clean_body(body) and sha_matches(reviewed, head):
            return {
                "status": "clean",
                "head": head,
                "reviewed_commit": reviewed,
                "url": comment.get("html_url"),
            }
        normalized = body.lower().replace("’", "'")
        if any(phrase in normalized for phrase in FAILURE_PHRASES):
            return {
                "status": "error",
                "head": head,
                "message": body.splitlines()[0] if body else "Codex review failed",
                "url": comment.get("html_url"),
            }

    for reaction in results["reactions"]:
        user = (reaction.get("user") or {}).get("login")
        if (
            is_bot(user)
            and reaction.get("content") == "+1"
            and after_since(reaction.get("created_at"), since)
        ):
            return {"status": "clean", "head": head, "signal": "thumbs_up"}

    return None


def emit(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wait for a GitHub Codex review, optionally requesting one first."
    )
    parser.add_argument("--repo", help="OWNER/REPO; defaults to the current repository")
    parser.add_argument("--pr", type=int, help="PR number; defaults to the current branch PR")
    parser.add_argument("--timeout", type=int, default=600, help="seconds to wait (default: 600)")
    parser.add_argument("--interval", type=int, default=90, help="poll interval (default: 90)")
    parser.add_argument(
        "--initial-delay",
        type=int,
        help="seconds before the first check (default: 300 with --no-request, otherwise 0)",
    )
    parser.add_argument(
        "--no-request",
        action="store_true",
        help="wait for an automatically triggered review without posting a comment",
    )
    args = parser.parse_args()

    if (
        args.timeout < 1
        or args.interval < 1
        or (args.initial_delay is not None and args.initial_delay < 0)
    ):
        parser.error("--timeout/--interval must be positive and --initial-delay nonnegative")

    try:
        repo = resolve_repo(args.repo)
        pr_data = resolve_pr(repo, args.pr)
        pr = pr_data["number"]
        head = pr_data["headRefOid"]

        if args.no_request:
            request = {}
            head_commit = api(repo, "commits/{}".format(head))
            since = head_commit["commit"]["committer"]["date"]
            query_since = one_second_before(since)
            request_id = None
        else:
            request = request_review(repo, pr)
            since = request["created_at"]
            query_since = one_second_before(since)
            request_id = request["id"]
        initial_delay = (
            args.initial_delay
            if args.initial_delay is not None
            else (300 if args.no_request else 0)
        )
        print(
            "Waiting for {}Codex review on {}/pull/{} at {}...".format(
                "automatic " if args.no_request else "",
                repo,
                pr,
                head[:10],
            ),
            file=sys.stderr,
            flush=True,
        )
        if initial_delay:
            print(
                "First GitHub check in {} seconds.".format(initial_delay),
                file=sys.stderr,
                flush=True,
            )
            time.sleep(initial_delay)
        deadline = time.monotonic() + args.timeout

        while time.monotonic() < deadline:
            current = resolve_pr(repo, pr)
            if current["headRefOid"] != head:
                emit(
                    {
                        "status": "head_changed",
                        "requested_head": head,
                        "current_head": current["headRefOid"],
                    }
                )
                return 4

            results = get_results(repo, pr, query_since, request_id)
            outcome = classify(results, head, since)
            if outcome:
                if outcome.get("reviewed_commit"):
                    resolved = api(repo, "commits/{}".format(outcome["reviewed_commit"]))
                    if resolved["sha"] != head:
                        outcome = None
                if outcome and outcome.get("signal") == "thumbs_up":
                    outcome["url"] = request.get("html_url")
                latest = resolve_pr(repo, pr)
                if latest["headRefOid"] != head:
                    emit(
                        {
                            "status": "head_changed",
                            "requested_head": head,
                            "current_head": latest["headRefOid"],
                        }
                    )
                    return 4
            if outcome:
                emit(outcome)
                if outcome["status"] == "clean":
                    return 0
                return 10 if outcome["status"] == "findings" else 4
            time.sleep(min(args.interval, max(0, deadline - time.monotonic())))

        emit({"status": "timeout", "head": head, "waited_seconds": args.timeout})
        return 3
    except (CommandError, KeyError, json.JSONDecodeError, OSError, ValueError) as error:
        emit({"status": "error", "message": str(error)})
        return 4


if __name__ == "__main__":
    sys.exit(main())
