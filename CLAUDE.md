# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

There is no `requirements.txt`/`pyproject.toml` yet — dependencies live in the pre-existing conda env `langchain` (Python 3.12) at `/opt/miniconda3/envs/langchain`, which already has `langgraph`, `langchain-anthropic`, `langchain-openai`, `langchain-tavily`, and `discord.py` installed. Use its interpreter directly rather than system `python3`.

- Local smoke test (no Discord, no real API calls, no network): `/opt/miniconda3/envs/langchain/bin/python run_local.py` — runs the graph end to end against a fixed sample request, manually simulating both interrupt responses, and prints each persona's message trail plus final state.
- Run the Discord bot: `/opt/miniconda3/envs/langchain/bin/python discord_bot.py` — requires a `.env` file with at least `DISCORD_BOT_TOKEN` set.
- Install a missing package into that same env: `/opt/miniconda3/envs/langchain/bin/pip install <pkg>`.
- No test suite, linter, or build step exists yet.

## Architecture

A LangGraph state machine drives a "team" of agent personas (Lead, Scout, Content, Producer). A Discord bot posts each persona's output under its own name/avatar via a per-channel webhook, so one bot login appears in Discord as several distinct posters working together rather than a single bot answering.

### Graph shape (`graph.py`)
- Nodes: `lead`, `scout`, `content`, `producer`. `lead` is a pure router with no LLM call — `route_from_lead()` picks the next node solely from `state["stage"]` (see the `Stage` literal in `state.py`). `scout`/`content`/`producer` each set the *next* stage value when they finish and always edge back to `lead`, which re-routes from there.
- `content` and `producer` call `interrupt()` partway through the node to pause the graph and surface their output (the 3 draft options / the finished video) for human approval. The interrupt's payload is a standalone `{speaker, content}` dict, deliberately kept separate from `state["messages"]` (see below). On resume, the whole node function re-runs from the top and `interrupt()` returns the resume value instead of pausing again — so any code before the `interrupt()` call must stay side-effect-free/idempotent.
- Compiled with `InMemorySaver`. The intended upgrade path (not yet done) is `AsyncSqliteSaver` (`langgraph-checkpoint-sqlite`, already installed in the conda env) so paused runs survive a bot restart — right now a restart silently drops any thread that was mid-interrupt.

### State (`state.py`)
- `state["messages"]` uses an `operator.add` reducer, so it accumulates over the *entire* checkpointed thread history — every `invoke()`/`resume` call returns the full history so far, not just what changed. Every consumer must track how many messages it has already consumed and slice `messages[already_posted:]`; this bookkeeping is not automatic (see `posted_count` in `discord_bot.py` and `already_posted` in `run_local.py`).
- Each node's return explicitly tags its output with `speaker` (`SpeakerMessage`) rather than leaving the caller to infer who's talking.

### Discord layer (`discord_bot.py`)
- `channel.id` (stringified) is used directly as the LangGraph `thread_id` — one persistent thread per Discord channel. A later request in the same channel extends the same thread's checkpoint history rather than starting clean.
- The bot's own login only listens (`on_message`) and never posts directly. All persona output goes through a webhook named `"Content Team"`, auto-created per channel on first use (`channel.create_webhook`, requires the Manage Webhooks permission) and cached in the in-memory `webhooks` dict.
- `awaiting_resume[channel_id]` — set from whether the *previous* graph result contained `"__interrupt__"` — is the only signal deciding whether the next incoming message in that channel is an approval/answer (`Command(resume=message.content)`) or a brand-new content request (fresh initial state). There is no keyword or intent detection.
- `PERSONAS` maps each `speaker` value to a Discord username + placeholder avatar (ui-avatars.com initials); swap these for real branded avatars without touching anything else.

### Current build status
Lead's routing, both interrupt checkpoints, and the full Discord/webhook/pause-resume plumbing are real and working end to end. `scout`, `content`'s draft generation, and `producer`'s video generation are still stubs — no Tavily call, no LLM call, no HeyGen/edge-tts call yet. This was a deliberate sequencing choice: prove the graph shape and Discord wiring first, then implement each agent's real logic behind the same node interface one at a time. When filling one in, keep the node's return shape unchanged (still emit a `messages` entry with the correct `speaker`, still set the same `state` fields it currently owns) so nothing in the routing or Discord layer needs to change.
