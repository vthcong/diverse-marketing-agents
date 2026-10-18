---
paths:
  - "plugins/marketing-team/**"
  - ".claude-plugin/marketplace.json"
---

# marketing-team plugin notes

- The plugin is a copy of the team in `.claude/`, not the source of it. Agents, skills, hooks and `heygen.py` / `heygen_server.py` exist twice (the plugin folder can't reach `../`, and an install copies it into a cache). Edit both, or the two drift. The `scout-tavily` experiment, `tidy`, `smoke-test` and the dev hooks (`smoke_gate`, `py_syntax_check`, `session_next_task`, `prompt_secret_guard`) are deliberately not shipped.
- Plugin agents ignore `permissionMode`, `hooks`, `mcpServers` and `initialPrompt`. The render gate therefore lives in `hooks/hooks.json` (it guards every agent, not just the producer) and the servers in `.mcp.json`. The `ask` permission rule on `start_video_render` cannot ship in a plugin; keep it in the project settings.
- Plugin MCP tools are named `mcp__plugin_marketing-team_<server>__<tool>`: use that in agent `tools:` and hook matchers. A stale name does not error, the tool is just missing. Agent `skills:` entries are namespaced too (`marketing-team:spoken-script`), tested on 2026-10-18 by spawning `marketing-team:producer` as a subagent. `skills:` is not preloaded for a main-thread `--agent` run, with or without the plugin.
- Hooks read the project through `CLAUDE_PROJECT_DIR` and keep counters in `CLAUDE_PLUGIN_DATA` (`hooks/paths.py`), never in the plugin folder, which an update replaces. The MCP server starts in the project folder, so `heygen.py` loads `.env` and the server finds `workspace/` from the current directory.
- Check with `claude plugin validate ./plugins/marketing-team` and `claude plugin validate .` (the marketplace). Installed at local scope: `claude plugin marketplace add ./ --scope local`, then `claude plugin install marketing-team@marketing-agents --scope local`.
