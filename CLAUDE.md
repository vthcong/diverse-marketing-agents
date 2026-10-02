# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Dependencies are pinned in `requirements.txt` and already installed in the conda env `langchain` (Python 3.12) at `/opt/miniconda3/envs/langchain`. Use that interpreter directly rather than system `python3`.

- Run the Discord bot: `/opt/miniconda3/envs/langchain/bin/python discord_bot.py`. `.env` needs `DISCORD_BOT_TOKEN`, `OPENAI_API_KEY` (every agent is an LLM; `llm.py` builds the clients at import, so it fails at startup without it), `TAVILY_API_KEY` (Scout's search) and `HEYGEN_API_KEY` / `HEYGEN_AVATAR_ID` / `HEYGEN_VOICE_ID` (video).
- Install a missing package into that same env: `/opt/miniconda3/envs/langchain/bin/pip install <pkg>`.
- No test suite or linter is checked in. To exercise the whole graph without Discord or a real OpenAI key: set a dummy `OPENAI_API_KEY` before importing, replace each `llm.LLMS[persona]` with `ChatOpenAI(api_key="x", max_retries=0, http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(fake_openai)))`, replace `tools.TavilySearch` / `tools.TavilyExtract` and monkeypatch `tools.heygen_start` / `tools.heygen_status`, build the app with `async with AsyncSqliteSaver.from_conn_string(tmp) as saver: discord_bot.app = graph.build_graph(saver)`, put a fake hook in `discord_bot.webhooks[channel_id]`, and drive turns with `await discord_bot.handle_turn(fake_channel, "Name: text")`. The real client, tool-binding, structured-output and LangGraph paths all run; only the model's decisions are scripted.

## Error handling policy

Deliberately minimal: code does not defensively check or catch errors, it lets them raise. An exception in a turn propagates out of `handle_turn`, discord.py logs it as "Ignoring exception in on_message", and nothing is posted to the channel (so a failed turn looks like silence in Discord; look at the console). The next message on the thread recovers cleanly, because LangGraph discards the stalled step when given new input. The only kept exceptions to this: `llm._call_tool` turns a failing tool into text for the model (dead links and failed searches are routine for the researcher), and `TURN_TIMEOUT_SECONDS` / `RECURSION_LIMIT` in `discord_bot.py` bound hangs and runaway lead/specialist loops that would otherwise never raise (LangGraph's own default recursion limit is ~10000).

## Architecture

A LangGraph state machine drives a team of four LLM agents (Lead, Scout, Content, Producer). A Discord bot posts each agent's messages under its own name/avatar via a per-channel webhook, so one bot login appears as several distinct people working together.

### Turn model (`graph.py`)
- `START -> lead --(state["next_agent"])--> scout | content | producer | END`, and each specialist edges back to `lead`. One user message is one turn: lead routes, a specialist works and replies, lead hands off again or wraps up, and the turn ends at `END`.
- Lead drives a job through the pipeline on its own (research, drafts, Lead picks the draft, video script) and stops only under the stop rules in `skills/lead.md`: missing information, a judgment call that belongs to the user, or a blocked specialist. The user's only mandatory gate is approving the video script and render, which `start_video_render` also enforces in code. A full run is about 9 steps (`lead, scout, lead, content, lead, content(record pick), lead, producer, lead`), so keep `RECURSION_LIMIT` above that if the pipeline grows.
- There is no `interrupt()`. The thread is persisted by `AsyncSqliteSaver` (`checkpoints.sqlite`), so the user's next message simply starts the next turn with everything still in state. That is what lets the user address any agent at any time (by name, role, or by replying to its message) instead of only at fixed approval points.
- `lead` is an LLM call using `with_structured_output(Route)`: `next` (`scout`/`content`/`producer`/`finish`), `task` (instruction for that specialist), `brief` (updated job summary, empty = unchanged) and `message` (what Lead says to the user, empty = silent). A runaway lead/specialist loop is stopped by the `recursion_limit` the Discord layer passes with each turn.
- `build_graph(checkpointer)` is sync and takes an already-open `AsyncSqliteSaver`; `discord_bot.main()` opens it with `async with`, which also closes it on shutdown (the saver creates its own tables lazily). Node names must not equal state keys, which is why the copywriter node is `content` while no state key is called that.

### Agents, skills and models
- Each agent's behaviour lives in `skills/<persona>.md`, prefixed by the shared `skills/team.md` charter, and is read fresh on every call, so prompt edits apply to the next message without a restart. Skills refer to teammates by role, never by name, because the names in `personas.py` are configurable.
- `personas.py` is the single per-persona config: `model` (plus any other `ChatOpenAI` kwarg), `role` (one line, used in the roster every agent sees), and the Discord `username` / `avatar_url`. `llm_kwargs()` strips the non-LLM keys. Note langchain-openai silently drops `temperature` on gpt-5 models.
- `llm.py` holds the shared plumbing: `LLMS` (one client per persona, built at import), `agent_context` (roster + shared workspace + last 24 transcript messages + the user's latest message + the task), and `run_agent`, a manual tool-calling loop (parallel tool calls via `asyncio.gather`, tool errors returned to the model as text, raises if a persona is still calling tools after `MAX_TOOL_ROUNDS`).

### State and tools (`state.py`, `tools.py`)
- `state["messages"]` is the whole-thread transcript with an `operator.add` reducer; user turns are stored with `speaker="user"` and the Discord display name baked into the content. The rest of the state is a shared workspace (`brief`, `findings`, `drafts`, `chosen_draft`, `video_script`, `video_job_id`, `video_status`, `video_url`) that specialists write through tools.
- Tools write via a `Workspace` (reads see earlier writes from the same turn; writes are collected in `ws.updates` and returned as the node's state update). Scout: `web_search`, `read_page` (Tavily), `save_findings`. Content: `save_drafts`, `choose_draft`. Producer: `set_video_plan`, `start_video_render`, `check_video_status`.
- `set_video_plan` rejects scripts over `MAX_VIDEO_WORDS` (50): HeyGen has no max-duration setting, so script length is the only cap on video length (measured ~0.5 s per word).
- `start_video_render` costs credits, so it refuses if the script was written in the same turn (the user must see it and reply first), and refuses to re-render unless `replace_existing=True`.
- Renders run in the background: `start_video_render` returns immediately and `tools._watch_render` polls HeyGen, then calls the handler registered with `set_render_handler` as `handler(thread_id, result)`. `discord_bot.on_render_finished` records the result on the thread (`aupdate_state(..., as_node="lead")` with `next_agent="finish"`, under the thread lock) and posts it. The watcher does not survive a bot restart; `check_video_status` re-queries HeyGen by the saved job id (HeyGen video URLs expire, so it deliberately doesn't cache the URL). `tools.py` uses HeyGen's v3 API (`POST /v3/videos`, `GET /v3/videos/{id}`; the v1/v2 endpoints are deprecated and retire 2026-10-31), written from their docs but not yet run against a real account. `HEYGEN_AVATAR_ID` must be an avatar *look* id from `GET /v3/avatars/looks`, and `HEYGEN_VOICE_ID` a `voice_id` from `GET /v3/voices`.

### Discord layer (`discord_bot.py`)
- `channel.id` (stringified) is the LangGraph `thread_id`: one persistent conversation per text channel, independent of every other channel.
- The bot's login only listens; all agent output goes through a webhook (`WEBHOOK_NAME`), auto-created per channel (needs Manage Webhooks) and cached in `webhooks`. Posts disable mentions and are chunked under Discord's 2000-character limit.
- `handle_turn` runs `app.astream(..., stream_mode="updates")` and posts each agent's message the moment its node finishes. Turns in a channel are serialized with `tools.thread_lock(thread_id)`, which the render callback also takes; the turn timeout guarantees the lock is released even if a call hangs.
- `PERSONAS` avatar URLs are Discord CDN attachment links, which are signed and expire; host the images in `images/` somewhere permanent.
