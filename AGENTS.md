# AGENTS.md

A LangGraph team of four LLM agents (Lead, Scout, Content, Producer) that runs marketing campaigns in Discord. See `docs/architecture.md` for how the graph, tools and Discord layer fit together.

## Commands

Dependencies are pinned in `requirements.txt` and already installed in the conda env `langchain` (Python 3.12) at `/opt/miniconda3/envs/langchain`. Use that interpreter directly rather than system `python3`.

- Run the Discord bot: `/opt/miniconda3/envs/langchain/bin/python discord_bot.py`. `.env` needs `DISCORD_BOT_TOKEN`, `OPENAI_API_KEY` (every agent is an LLM; `llm.py` builds the clients at import, so it fails at startup without it), `TAVILY_API_KEY` (Scout's search) and `HEYGEN_API_KEY` / `HEYGEN_AVATAR_ID` / `HEYGEN_VOICE_ID` (video).
- Never read or print `.env`; it holds live credentials.

## Testing

No test suite or linter is checked in. To exercise the whole graph without Discord or a real OpenAI key: set a dummy `OPENAI_API_KEY` before importing, replace each `llm.LLMS[persona]` with `ChatOpenAI(api_key="x", max_retries=0, http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(fake_openai)))`, replace `tools.TavilySearch` / `tools.TavilyExtract` and monkeypatch `tools.heygen_start` / `tools.heygen_status`, build the app with `async with AsyncSqliteSaver.from_conn_string(tmp) as saver: discord_bot.app = graph.build_graph(saver)`, put a fake hook in `discord_bot.webhooks[channel_id]`, and drive turns with `await discord_bot.handle_turn(fake_channel, "Name: text")`. The real client, tool-binding, structured-output and LangGraph paths all run; only the model's decisions are scripted.

## Error handling policy

Deliberately minimal: code does not defensively check or catch errors, it lets them raise. An exception in a turn propagates out of `handle_turn`, discord.py logs it as "Ignoring exception in on_message", and nothing is posted to the channel (so a failed turn looks like silence in Discord; look at the console). The next message on the thread recovers cleanly, because LangGraph discards the stalled step when given new input. The only kept exceptions to this: `llm._call_tool` turns a failing tool into text for the model (dead links and failed searches are routine for the researcher), and `TURN_TIMEOUT_SECONDS` / `RECURSION_LIMIT` in `discord_bot.py` bound hangs and runaway lead/specialist loops that would otherwise never raise (LangGraph's own default recursion limit is ~10000).
