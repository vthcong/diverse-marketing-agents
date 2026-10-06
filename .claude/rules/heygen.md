---
paths:
  - "tools.py"
---

# HeyGen v3 notes

`tools.py` calls HeyGen's v3 API (`POST /v3/videos`, `GET /v3/videos/{id}`). v1/v2 retire 2026-10-31, so don't reintroduce them.

- Written from HeyGen's docs and not yet run against a real account. Treat field names and response shapes (`data.video_id`, `data.status`, `video_url`, `failure_message`) as unverified until a real render succeeds.
- `HEYGEN_AVATAR_ID` must be an avatar *look* id from `GET /v3/avatars/looks`, not an avatar group id. `HEYGEN_VOICE_ID` must be a `voice_id` from `GET /v3/voices`.
- HeyGen has no max-duration setting, so script word count is the only cap on video length (~0.5 s per word). Keep the `MAX_VIDEO_WORDS` check in `set_video_plan`.
- Renders cost credits. `start_video_render` must keep refusing when the script was written in the same turn (the user has to see it first) and refuse to re-render unless `replace_existing=True`. Don't weaken either check.
- Video URLs expire, so never cache `video_url` as a long-lived value. `check_video_status` re-queries by the saved job id.
- `_watch_render` does not survive a bot restart. A render started before a restart is only recovered through `check_video_status`.
