---
paths:
  - "llm.py"
  - "personas.py"
---

# LLM and persona config notes

- `personas.py` is the single per-persona config: `model` plus any `ChatOpenAI` kwarg, and the non-LLM keys `role`, `username`, `avatar_url` (filtered out by `_NON_LLM_KEYS`). A new non-LLM key must be added to `_NON_LLM_KEYS`, or it is passed to `ChatOpenAI`.
- Skills are not copied into `personas/`. A persona's `skills` list names folders in `.claude/skills/`, the same files Claude Code reads. `system_prompt` shows only the catalog (name and description); `run_agent` adds a `load_skill` tool that fetches the full text, or an extra file like `reference.md`, on demand. Leave lead's list empty: its routing call is a single structured-output call with no tool loop. Skills that assume Claude Code features (`campaign-brief`, which uses `!` injection and `$ARGUMENTS`) don't belong in any list.
- langchain-openai silently drops `temperature` on gpt-5 models, so setting it can be a no-op. Check it takes effect before relying on it.
- `avatar_url` values are Discord CDN attachment links, which are signed and expire. Host the images in `images/` somewhere permanent instead of pasting new CDN links.
- An agent only knows what `agent_context` shows it, trimmed by `TRANSCRIPT_MESSAGES`, `TRANSCRIPT_CHARS` and `FINDINGS_CHARS`. If an agent "forgets" something, check those limits before blaming the prompt.
