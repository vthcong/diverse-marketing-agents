---
paths:
  - "graph.py"
  - "state.py"
---

# Graph and state notes

- Node names must not equal state keys (LangGraph rejects it). Name a new node something that isn't a `State` field.
- There is no `interrupt()`. `AsyncSqliteSaver` persists the thread, so the user's next message starts the next turn with everything still in state. That is what lets the user address any agent at any time. Don't add a blocking approval step; the only gate is the render approval in `start_video_render`.
- `build_graph(checkpointer)` is sync and takes an already-open `AsyncSqliteSaver`. `discord_bot.main()` opens it with `async with`.
- Adding a workspace field to `State` touches three more places, or the field silently misbehaves:
  - the `new_job` reset in `lead()` if it belongs to one deliverable (research like `findings` and the `brief` deliberately survive);
  - `render_workspace` in `llm.py`, or no agent will ever see it;
  - a tool that writes it through `ws.set`, since a specialist's state update is only `ws.updates` plus its message.
- Lead/specialist ping-pong is cut off in code by `MAX_REPLIES_PER_TURN`; `RECURSION_LIMIT` in `discord_bot.py` is the last-resort backstop. A full run is about 9 steps, so raise `RECURSION_LIMIT` if you add pipeline stages.
