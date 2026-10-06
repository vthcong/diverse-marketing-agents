---
paths:
  - "discord_bot.py"
---

# Discord layer notes

- `str(channel.id)` is the LangGraph `thread_id`: one persistent conversation per text channel. Don't key state on anything else.
- Anything that writes a thread's state outside a graph turn (like `on_render_finished`) must hold `tools.thread_lock(thread_id)`. A graph turn and a finishing render writing the same thread at once would corrupt its state. `TURN_TIMEOUT_SECONDS` is what guarantees a hung call can't hold the lock forever, so keep every turn under it.
- Creating the per-channel webhook needs the bot to have Manage Webhooks. The `message_content` intent is privileged and must also be switched on in the Discord developer portal, or the bot receives empty messages.
- When a render finishes, `on_render_finished` writes the result with `as_node="lead"` and `next_agent="finish"` so the thread has no pending step. Keep both when changing it.
