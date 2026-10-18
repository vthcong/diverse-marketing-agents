---
description: Draft a campaign brief (deliverables, platform, audience, tone, constraints) for a marketing job
when_to_use: Use when the user asks to draft, write or start a brief, campaign, post, caption or video for a brand or product, e.g. "draft a brief for a coffee brand", "plan a LinkedIn hiring post", "start a campaign for our launch"
argument-hint: "[brand] [channel]"
arguments: [brand, channel]
allowed-tools: Bash(ls *)
---

Write a campaign brief for **$brand** on **$channel**. Full request as typed: $ARGUMENTS

If `$brand` or `$channel` is empty, infer it from the request. If it can't reasonably be inferred, ask the single most important question and stop. Never invent a brand, audience or fact the user didn't give you.

Jobs already in the workspace (don't overwrite one without being asked):

!`ls workspace 2>/dev/null || echo "(no jobs yet)"`

Fill in the template at `${CLAUDE_SKILL_DIR}/template.md`:

1. Replace every `<...>` placeholder. If a section can't be filled from the request, write `TBD: <the question to ask the user>`.
2. Keep the `## Brief` paragraph to 3-4 sentences. It is the text the team passes around, so it must stand alone.
3. List every claim you can't verify (salary, stats, dates, benefits) under *Claims to verify*. Never state one as fact.
4. Save it to `workspace/<job-name>/brief.md` (lowercase, hyphenated job name) and show the brief to the user.

The brief only scopes the job. Don't research or write copy here.
