# AGENTS.md

A LangGraph team of four LLM agents (Lead, Scout, Content, Producer) that runs marketing campaigns in Discord. See `docs/architecture.md` for how the graph, tools and Discord layer fit together.

## Commands

Dependencies are pinned in `requirements.txt` and already installed in the conda env `langchain` (Python 3.12) at `/opt/miniconda3/envs/langchain`. Use that interpreter directly rather than system `python3`.

- Run the Discord bot: `/opt/miniconda3/envs/langchain/bin/python discord_bot.py`. `.env` needs `DISCORD_BOT_TOKEN`, `OPENAI_API_KEY` (every agent is an LLM; `llm.py` builds the clients at import, so it fails at startup without it), `TAVILY_API_KEY` (Scout's search) and `HEYGEN_API_KEY` / `HEYGEN_AVATAR_ID` / `HEYGEN_VOICE_ID` (video).
- Never read or print `.env`; it holds live credentials.

## Testing

No linter is checked in. The one test is `scripts/smoke_test.py`: run `/opt/miniconda3/envs/langchain/bin/python scripts/smoke_test.py`, or the `/smoke-test` skill. It drives two full turns through `discord_bot.handle_turn` with no Discord or real API keys: a dummy `OPENAI_API_KEY`, each `llm.LLMS[persona]` swapped for a `ChatOpenAI` over `httpx.MockTransport`, and Tavily, HeyGen and the webhook faked. The real client, tool-binding, structured-output and LangGraph paths all run; only the model's decisions are scripted. The `Stop` hook `.claude/hooks/smoke_gate.py` runs it whenever the code has changed.

## Error handling policy

Deliberately minimal: code does not defensively check or catch errors, it lets them raise. An exception in a turn propagates out of `handle_turn`, discord.py logs it as "Ignoring exception in on_message", and nothing is posted to the channel (so a failed turn looks like silence in Discord; look at the console). The next message on the thread recovers cleanly, because LangGraph discards the stalled step when given new input. The only kept exceptions to this: `llm._call_tool` turns a failing tool into text for the model (dead links and failed searches are routine for the researcher), and `TURN_TIMEOUT_SECONDS` / `RECURSION_LIMIT` in `discord_bot.py` bound hangs and runaway lead/specialist loops that would otherwise never raise (LangGraph's own default recursion limit is ~10000).
