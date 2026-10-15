---
description: Run the mocked end-to-end smoke test of the LangGraph team (no Discord, no real API keys) and report a pass or fail verdict
allowed-tools: Bash(/opt/miniconda3/envs/langchain/bin/python scripts/smoke_test.py)
disable-model-invocation: true
context: fork
background: false
---

Run the smoke test from the repo root:

```
/opt/miniconda3/envs/langchain/bin/python scripts/smoke_test.py
```

It drives two full turns through `discord_bot.handle_turn` with OpenAI, Tavily, HeyGen and Discord faked. Do not read or print `.env`, and do not edit any file.

Reply with the verdict only, in at most five lines:

- **Pass:** the `SMOKE TEST PASSED: ...` line.
- **Fail:** the last line of the traceback (the exception and its message), plus the `scripts/smoke_test.py` line number it points at. If it is a `Connection error` from `openai.APIConnectionError`, look further up the traceback for the real cause (usually `... made more model requests than its script has steps`) and report that instead.

Ignore the `LangChainPendingDeprecationWarning`, `UserWarning` and `http_socket_options` lines. They are harmless noise.
