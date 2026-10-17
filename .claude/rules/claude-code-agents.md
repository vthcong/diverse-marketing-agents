---
paths:
  - ".claude/agents/*.md"
---

# Claude Code agent notes

- The scout's research file is `workspace/<job>/scout_findings.md`, never plain `findings.md`. Claude Code subagents are blocked from writing files with report-style names: the write fails with "Subagents should return findings as text, not write report files". Tested on 2026-10-17: `findings.md`, `FINDINGS.md`, `summary.md`, `report.md` and `analysis.md` are rejected; `research.md`, `sources.md`, `notes.md`, `findings.txt`, `job_findings.md` and `scout_findings.md` are accepted. It is a check on the filename alone, not on the agent type, its tools, `permissionMode` or the agent-teams flag, and `drafts.md`, `chosen.md` and `video_script.md` are fine.
- Exact cause, read from the Claude Code 2.1.302 binary on 2026-10-17: the Write tool's `validateInput` rejects the call when it runs in a subagent (`agentId` is set) and the basename matches `/^(REPORT|SUMMARY|FINDINGS|ANALYSIS).*\.md$/i`. It runs before permissions, so no setting, allow rule or env var turns it off. Every subagent's system prompt also says "Do NOT Write report/summary/findings/analysis .md files". The main thread (including `claude --agent lead`) has no `agentId`, so it can write `findings.md`.
- Only Write has the check: a subagent can Read and Edit an existing `findings.md` (tested). Don't build on that gap; it goes against the harness's intent, needs someone else to create the file first, and could be closed in any release.
- Do not rename `scout_findings.md` back to `findings.md`, and do not name any other specialist file so that it starts with `summary`, `report` or `analysis` and ends in `.md` (`job_report.md` is fine, `report_v2.md` is not).
- The Python bot is not affected: its `save_findings` tool writes to graph state, not to a file.
