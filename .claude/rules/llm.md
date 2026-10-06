---
paths:
  - "llm.py"
  - "personas.py"
---

# LLM and persona config notes

- `personas.py` is the single per-persona config: `model` plus any `ChatOpenAI` kwarg, and the non-LLM keys `role`, `username`, `avatar_url` (filtered out by `_NON_LLM_KEYS`). A new non-LLM key must be added to `_NON_LLM_KEYS`, or it is passed to `ChatOpenAI`.
- langchain-openai silently drops `temperature` on gpt-5 models, so setting it can be a no-op. Check it takes effect before relying on it.
- `avatar_url` values are Discord CDN attachment links, which are signed and expire. Host the images in `images/` somewhere permanent instead of pasting new CDN links.
- An agent only knows what `agent_context` shows it, trimmed by `TRANSCRIPT_MESSAGES`, `TRANSCRIPT_CHARS` and `FINDINGS_CHARS`. If an agent "forgets" something, check those limits before blaming the prompt.
