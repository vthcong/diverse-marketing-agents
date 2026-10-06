# personas/

These files are the agents' system prompts. The LangGraph bot sends `team.md` followed by `<persona>.md` on every call (`load_team` / `load_persona` in `personas.py`).

- Refer to teammates by role (the researcher, the copywriter, the video producer, the lead), never by name. The names in `personas.py` are configurable.
- Put a rule that every agent must follow in `team.md`, and a rule for one agent in that agent's file. Don't copy a rule into several files.
- A persona file must be named exactly like its key in `PERSONAS` in `personas.py` (`lead.md`, `scout.md`, `content.md`, `producer.md`), because the loader builds the path from the key.
- Files are read fresh on every call, so edits apply to the next message without restarting the bot.
