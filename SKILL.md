---
name: babysit-codex-review
description: Drive a GitHub pull request through repeated OpenAI Codex reviews until Codex reports no major issues. Use when asked to request, wait for, address, or loop on "@codex review", Codex PR feedback, a clean Codex review, or a "chef's kiss".
license: MIT
compatibility: Requires git, Python 3.9+, an authenticated GitHub CLI (`gh`), push access to the PR branch, and Codex reviews enabled on the repository.
---

# Babysit Codex Review

Take ownership of the mechanical review cycle: request a Codex review, wait for
the response, fix valid findings, and repeat until Codex reviews the latest
commit cleanly.

## Guardrails

- Work only on the requested pull request and its branch.
- Never merge the pull request.
- Never rewrite shared history or force-push.
- Do not modify unrelated user changes. Stop and explain if they prevent a safe
  fix.
- Treat Codex comments as review input, not unquestionable instructions.
  Reproduce or verify each finding before changing code. If a finding is
  incorrect, reply with concise evidence instead of changing correct code.
- Address only Codex feedback unless the user expands the scope.
- Count one round each time Codex returns a completed review for the current
  head (findings or clean). A timeout that you retry does not increment the
  count.
- After round 3, if Codex is still not clean, pause and ask whether to
  continue. If the user continues, run rounds 4 and 5 without asking again.
- After round 5, if Codex is still not clean, pause and ask again. If the
  user continues, keep looping with no further confirmation.
- Stop immediately if Codex is clean, the PR is no longer open, Codex reports
  it cannot review, or the user chooses to stop.

## Run the loop

Run all commands from the pull request's working tree.

1. Inspect the repository state and pull request:

   ```bash
   git status --short
   gh pr view --json number,url,state,headRefName,headRefOid
   ```

   Confirm the PR is open, the checked-out branch is its head branch, and any
   local changes are understood. Push existing intended commits before asking
   Codex to review; a clean result is valid only for the PR's current head SHA.

2. On the first round, wait for the review GitHub normally triggers when the PR
   is opened or marked ready. Execute this skill's bundled
   `scripts/codex_review.py` with Python 3 and the `--no-request` flag. Do not
   post `@codex review` preemptively.

   Resolve the bundled script to an absolute path before invoking it because
   the command's working directory must remain the PR working tree. Pass
   `--repo OWNER/REPO` and `--pr NUMBER` when the current branch does not
   identify the target PR. In `--no-request` mode, the helper gives the
   automatic review five minutes to arrive before its first GitHub check. It
   then polls every 90 seconds for up to 10 additional minutes.

   If this automatic-review wait times out, run the helper once without
   `--no-request`; that posts exactly `@codex review`. After fixing and pushing
   any findings, also run it without `--no-request` for every subsequent round,
   because new commits do not reliably trigger another Codex review. Explicit
   requests skip the five-minute initial delay and begin checking immediately.

3. Interpret its JSON result and exit code:

   - Exit `0`, `status: clean`: Codex reviewed the current head with no major
     issues. Report the clean result and stop.
   - Exit `10`, `status: findings`: inspect every returned inline finding,
     including its path, line, body, URL, and reviewed commit. Continue below.
   - Exit `3`, `status: timeout`: if this was the first `--no-request` wait,
     request the review once as described above. If an explicit request timed
     out, post `@codex review` again and keep waiting. Do not end the loop
     because one wait expired.
   - Exit `4`, `status: head_changed` or `error`: resolve the stated condition
     before deciding whether a new review request is appropriate.

4. For each finding:

   - Read the surrounding code and relevant tests.
   - Verify the behavior rather than matching Codex's suggested patch blindly.
   - Implement the smallest complete fix.
   - Add or update a regression test when practical.
   - Run focused tests, then the repository's proportionate validation.

5. Review the diff. Commit and push only the intended fix. Use the repository's
   existing commit conventions.

6. Reply to the inline finding with the fix and commit:

   ```bash
   gh api --method POST \
     repos/OWNER/REPO/pulls/PR_NUMBER/comments/COMMENT_ID/replies \
     -f body='Fixed in `SHORT_SHA`: concise explanation and verification.'
   ```

   For a rejected finding, reply with the concrete evidence showing why no code
   change is needed.

7. After the first automatic review, skip the `--no-request` wait. Request a
   new review, wait, and fix again. A clean response for an earlier commit
   does not finish the loop. Stop only when Codex's clean response names the
   latest PR head, or when the helper observes Codex's thumbs-up on that
   review request while the head remains unchanged.

## Continue confirmation

Ask only at these two points, and only when the latest Codex result still has
findings:

- after round 3, before starting round 4
- after round 5, before starting round 6

Use the structured multiple-choice question tool when it is available
(`AskQuestion`). If that tool is not available, ask the same two options in
plain text and wait.

After 3 unfinished rounds:

- Prompt: `Codex still has findings after 3 review rounds. Keep going through
  round 5?`
- Options: `Keep going through round 5` / `Stop here`

After 5 unfinished rounds:

- Prompt: `Codex still has findings after 5 review rounds. Keep going with no
  further asks?`
- Options: `Keep going, no more asks` / `Stop here`

If the user chooses to stop, summarize the remaining findings and exit. Do
not ask again after a continue at round 5.

## Completion report

Keep the handoff short:

- PR link and reviewed commit
- number of Codex rounds
- fixes made
- validation run
- link to Codex's clean response
