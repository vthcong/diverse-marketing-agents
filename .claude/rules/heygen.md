---
paths:
  - "tools.py"
  - "heygen.py"
  - "mcp_servers/heygen_server.py"
---

# HeyGen v3 notes

`heygen.py` (shared by the Discord bot's `tools.py` and `mcp_servers/heygen_server.py`) calls HeyGen's v3 API (`POST /v3/videos`, `GET /v3/videos/{id}`). v1/v2 retire 2026-10-31, so don't reintroduce them.

- Written from HeyGen's docs and not yet run against a real account. Treat field names and response shapes (`data.video_id`, `data.status`, `video_url`, `failure_message`) as unverified until a real render succeeds.
- `HEYGEN_AVATAR_ID` must be an avatar *look* id from `GET /v3/avatars/looks`, not an avatar group id. `HEYGEN_VOICE_ID` must be a `voice_id` from `GET /v3/voices`.
- HeyGen has no max-duration setting, so script word count is the only cap on video length (~0.5 s per word). Keep the `MAX_VIDEO_WORDS` check in `set_video_plan`.
- Renders cost credits. `start_video_render` must keep refusing when the script was written in the same turn (the user has to see it first) and refuse to re-render unless `replace_existing=True`. Don't weaken either check.
- A render is identified by `render_fingerprint` (script, avatar id, voice id, resolution, aspect ratio), saved next to the job id (`video_fingerprint` in graph state, `fingerprint` in `render.json`). `start_video_render` refuses only when the saved render is `rendering`/`completed` with the same fingerprint, so editing the script or switching avatar/voice renders without `replace_existing`. A render with no saved fingerprint (made before this existed) still blocks. When you add anything to the HeyGen payload that changes the video, add it to the fingerprint too.
- Video URLs expire, so never cache `video_url` as a long-lived value. `check_video_status` re-queries by the saved job id.
- `_watch_render` does not survive a bot restart. A render started before a restart is only recovered through `check_video_status`.
- The MCP server has the same watcher (`_watch_render` in `heygen_server.py`): it polls every 60 s for up to 15 min, saves the result in `render.json`, and posts the link through `post_as` when `start_video_render` was given a `chat_id`. It dies with the server process, so the server must stay registered in `.mcp.json` (session level). Registered inline in a subagent's `mcpServers`, Claude Code shuts it down when the subagent finishes and the watcher goes with it. The watcher stops quietly if `render.json` no longer says `rendering` for its job id, so a `check_video_status` that already told the user, or a replacement render, never causes a duplicate post. The poll constants are duplicated from `tools.py`; change both.
- `plugins/marketing-team/servers/heygen_server.py` has not been given the watcher: the plugin ships no Discord poster. Add one there before relying on it from the plugin.
