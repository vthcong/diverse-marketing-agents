# Architecture

A LangGraph state machine drives four LLM agents (Lead, Scout, Content, Producer). A Discord bot posts each agent's messages under its own name/avatar via a per-channel webhook, so one bot login appears as several people.

## Turn model (`graph.py`)
- `START -> lead --(state["next_agent"])--> scout | content | producer | END`, and each specialist edges back to `lead`. One user message is one turn.
- Lead drives a job through the pipeline on its own (research, drafts, pick, video script) and stops only under the stop rules in `personas/lead.md`. The user's only mandatory gate is approving the video script and render, which `start_video_render` also enforces in code.
- `lead` uses `with_structured_output(Route)`; `new_job=True` clears the previous deliverable but keeps research.

## Agents and personas
- Each agent's prompt is `personas/<persona>.md` prefixed by `personas/team.md`, read fresh on every call, so prompt edits apply without a restart.
- `personas.py` is the single per-persona config. `llm.py`'s `run_agent` is a manual tool-calling loop that raises past `MAX_TOOL_ROUNDS`.

## State and tools (`state.py`, `tools.py`)
- Tools write through a `Workspace`: reads see earlier writes from the same turn, writes are collected in `ws.updates` and returned as the node's state update.
- Renders run in the background: `tools._watch_render` polls HeyGen, then calls the handler registered with `set_render_handler` (`discord_bot.on_render_finished`).

## Discord layer (`discord_bot.py`)
- One persistent conversation per text channel; the bot's login only listens and all agent output goes through a webhook.

## Path-scoped rules
Details that only matter when editing a file live in `.claude/rules/` and load only when that file is read: `graph.md` (`graph.py`, `state.py`), `llm.md` (`llm.py`, `personas.py`), `discord.md` (`discord_bot.py`), `heygen.md` (`tools.py`, `heygen.py`, `mcp_servers/heygen_server.py`).
