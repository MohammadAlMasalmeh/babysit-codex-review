# Babysit Codex Review

An [Agent Skill](https://agentskills.io) that requests OpenAI Codex reviews on
GitHub pull requests, waits for the response, fixes valid findings, and repeats
until Codex reviews the latest commit cleanly.

After install, invoke `/babysit-codex-review`.

## Download / install

Any agent that can run a shell can install this. Prefer the Skills CLI; it
copies the folder into every supported client on the machine (Cursor, Claude
Code, Codex, OpenCode, and others).

### From a local checkout of this directory

```bash
npx skills add /absolute/path/to/babysit-codex-review --all -g --copy
```

From inside this directory:

```bash
npx skills add . --all -g --copy
```

### From a ZIP

```bash
unzip babysit-codex-review.zip
npx skills add ./babysit-codex-review --all -g --copy
```

### From GitHub

```bash
npx skills add MohammadAlMasalmeh/babysit-codex-review --all -g --copy
```

Also accepted:

```bash
npx skills add https://github.com/MohammadAlMasalmeh/babysit-codex-review
```

`-g` installs for the current user. `--all` targets every detected agent.
`--copy` writes real files instead of symlinks.

### If the Skills CLI is unavailable

Copy this whole directory (the folder that contains `SKILL.md`) to one of these
locations, keeping the folder name `babysit-codex-review`:

| Scope | Path |
| --- | --- |
| All Agent Skills clients, this user | `~/.agents/skills/babysit-codex-review/` |
| Cursor, this user | `~/.cursor/skills/babysit-codex-review/` |
| Claude Code, this user | `~/.claude/skills/babysit-codex-review/` |
| Codex, this user | `~/.codex/skills/babysit-codex-review/` |
| This repository only | `.agents/skills/babysit-codex-review/` or `.cursor/skills/babysit-codex-review/` |

```bash
mkdir -p ~/.agents/skills ~/.cursor/skills
cp -R babysit-codex-review ~/.agents/skills/babysit-codex-review
cp -R babysit-codex-review ~/.cursor/skills/babysit-codex-review
```

Clients that import `.skill` bundles can load `babysit-codex-review.skill`
directly. That file is a zip of this directory.

Start a new agent chat after installing. Slash commands are discovered at
session start, not mid-conversation.

## Requirements

- Python 3.9+
- `git`
- Authenticated GitHub CLI (`gh auth login`)
- Push access to the pull request branch
- Codex reviews enabled for the GitHub repository

## Use

Type `/babysit-codex-review` in an agent that exposes skills as slash commands.
Otherwise ask the agent to babysit the Codex review on the current pull request.

The polling helper can also be invoked directly:

```bash
# First review: wait for GitHub's automatic Codex review.
python3 scripts/codex_review.py --repo OWNER/REPO --pr 123 --no-request

# Later rounds: request a fresh review after pushing fixes.
python3 scripts/codex_review.py --repo OWNER/REPO --pr 123
```

The automatic first-review mode waits five minutes before its first check,
then polls every 90 seconds for up to 10 additional minutes. Explicit requests
post `@codex review`, skip the initial delay, and use the same polling cadence.
The helper exits `0` for a clean review, `10` for findings, `3` for a timeout,
or `4` for an environmental error or changed PR head.
