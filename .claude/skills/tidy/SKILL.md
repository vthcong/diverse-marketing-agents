---
description: Review the repo for orphaned files, stale comments and dead code left behind by design changes, and report findings without editing anything
argument-hint: "[path to limit the review, default the whole repo]"
allowed-tools: Read, Grep, Glob, Bash(git status *), Bash(git log *), Bash(git diff *)
disable-model-invocation: true
context: fork
background: false
---

Review `$ARGUMENTS` (the whole repo if empty) for leftovers from designs that were changed or dropped. Report only: never edit, delete or move anything, and never read `.env`, `checkpoints.sqlite*`, `workspace/` job files or `.claude/agent-memory/`.

## What to look for

**1. Orphaned files.** A file is an orphan only if nothing references it by path, module name or script name in: Python code, `.claude/settings*.json`, `.mcp.json`, agent frontmatter, `personas/`, `.claude/rules/` or `docs/`. Skills, agents and rules are found by folder convention, so judge those by whether anything still describes or relies on them. Entry points (`discord_bot.py`, `scripts/*`) are not orphans.

**2. Stale comments and docstrings.** Flag a comment that mentions something that no longer exists or was replaced ("no longer", "used to", "previously", "instead of X" where X is gone, names of deleted files or functions). Flag one that restates the next line, narrates history (git has it), or is a finished TODO. Keep comments that explain why. Keep this repo's style: one long comment stays on one line.

**3. Dead code.** Functions, constants, imports and variables with no caller. Grep config files and strings too, because hooks and personas are wired up from config, not imports.

**4. Docs.** In `docs/claude-code-learning-path.md`, flag `Notes:` text that narrates a dropped design in detail. Propose a shorter version that keeps the one-clause reason it was dropped. Never touch the ticked boxes or task wording.

## Check before you report

For each candidate, grep for it and read the hits. Say what you searched. Do not flag something because it merely looks unused.

## Report

Group findings as **Orphaned files**, **Stale comments**, **Dead code**, **Docs**. Each finding: `path:line`, what it is, the evidence, and a confidence of high (no references anywhere) or medium. Then a **Needs your confirmation** list: anything where the answer depends on the user's intent (for example, a file kept for a later task). End with the question "Which of these should I apply?" and wait.
