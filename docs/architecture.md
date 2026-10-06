# Architecture

A LangGraph state machine drives four LLM agents (Lead, Scout, Content, Producer). A Discord bot posts each agent's messages under its own name/avatar via a per-channel webhook, so one bot login appears as several people.

## Turn model (`graph.py`)
- `START -> lead --(state["next_agent"])--> scout | content | producer | END`, and each specialist edges back to `lead`. One user message is one turn.
- Lead drives a job through the pipeline on its own (research, drafts, pick, video script) and stops only under the stop rules in `personas/lead.md`. The user's only mandatory gate is approving the video script and render, which `start_video_render` also enforces in code. A full run is about 9 steps, so keep `RECURSION_LIMIT` above that if the pipeline grows.
- There is no `interrupt()`. The thread is persisted by `AsyncSqliteSaver` (`checkpoints.sqlite`), so the user's next message starts the next turn with everything still in state. That is what lets the user address any agent at any time.
- `lead` uses `with_structured_output(Route)`. `new_job=True` clears `drafts`, `chosen_draft` and the video fields but keeps research. A lead/specialist ping-pong is cut off in code: if lead routes to a specialist who has already replied `MAX_REPLIES_PER_TURN` (2) times since the user's latest message, `lead()` forces `finish` and drops its own message. `RECURSION_LIMIT` is the last-resort backstop.
- `build_graph(checkpointer)` is sync and takes an already-open `AsyncSqliteSaver`; `discord_bot.main()` opens it with `async with`. Node names must not equal state keys, which is why the copywriter node is `content`.

## Agents, personas and models
- Each agent's prompt is `personas/<persona>.md` prefixed by `personas/team.md`, read fresh on every call, so prompt edits apply without a restart.
- `personas.py` is the single per-persona config (`model` plus any `ChatOpenAI` kwarg, `role`, Discord `username` / `avatar_url`). langchain-openai silently drops `temperature` on gpt-5 models.
- `llm.py`: `run_agent` is a manual tool-calling loop that raises if a persona is still calling tools after `MAX_TOOL_ROUNDS`.

## State and tools (`state.py`, `tools.py`)
- User turns are stored in `state["messages"]` with `speaker="user"` and the Discord display name baked into the content.
- Tools write through a `Workspace`: reads see earlier writes from the same turn, writes are collected in `ws.updates` and returned as the node's state update.
- `set_video_plan` rejects scripts over `MAX_VIDEO_WORDS` (50): HeyGen has no max-duration setting, so script length is the only cap (~0.5 s per word).
- `start_video_render` costs credits, so it refuses if the script was written in the same turn (the user must see it and reply first), and refuses to re-render unless `replace_existing=True`.
- Renders run in the background: `tools._watch_render` polls HeyGen, then calls the handler registered with `set_render_handler`. `discord_bot.on_render_finished` records the result on the thread (`aupdate_state(..., as_node="lead")` with `next_agent="finish"`, under the thread lock) and posts it. The watcher does not survive a bot restart; `check_video_status` re-queries HeyGen by the saved job id (video URLs expire, so the URL is deliberately not cached).
- `tools.py` uses HeyGen's v3 API (`POST /v3/videos`, `GET /v3/videos/{id}`; v1/v2 retire 2026-10-31), written from their docs but not yet run against a real account. `HEYGEN_AVATAR_ID` must be an avatar *look* id from `GET /v3/avatars/looks`, and `HEYGEN_VOICE_ID` a `voice_id` from `GET /v3/voices`.

## Discord layer (`discord_bot.py`)
- `channel.id` (stringified) is the LangGraph `thread_id`: one persistent conversation per text channel.
- The bot's login only listens; all agent output goes through a webhook auto-created per channel (needs Manage Webhooks).
- Turns in a channel are serialized with `tools.thread_lock(thread_id)`, which the render callback also takes; the turn timeout guarantees the lock is released even if a call hangs.
- `PERSONAS` avatar URLs are Discord CDN attachment links, which are signed and expire; host the images in `images/` somewhere permanent.
