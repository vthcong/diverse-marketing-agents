"""MCP server that exposes the HeyGen video tools to Claude Code.

State lives in files under workspace/<job>/: video_script.md is the spoken script and render.json holds the HeyGen job id, last known status and the fingerprint of what was rendered. The render approval gate is deliberately not here: it is a permission rule (5.2) and a hook (6.1).

A render is watched in the background, like tools._watch_render in the Discord bot: this server polls HeyGen, saves the result in render.json and, when start_video_render was given a chat_id, posts the link to that Discord channel. The watcher lives only as long as this server process, so the server must be a session-level one (.mcp.json), not an inline subagent one, which Claude Code shuts down when the subagent finishes.
"""
import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # a script run by path only has its own folder on sys.path, so the project root must be added to import heygen.py

from mcp.server.fastmcp import FastMCP

from heygen import (
    heygen_start,
    heygen_status,
    render_blocks_new_one,
    render_exists_message,
    render_fingerprint,
    script_length_error,
    status_message,
)
from mcp_servers.discord_persona_server import post_as  # the same webhook poster the agents use, so the finished link comes from the producer's own name and avatar

WORKSPACE = ROOT / "workspace"
RENDER_POLL_SECONDS = 60  # the same cadence as tools.py in the Discord bot
RENDER_TIMEOUT_SECONDS = 15 * 60

mcp = FastMCP("heygen")

_background: set[asyncio.Task] = set()


def _job_dir(job: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", job):  # the job name comes from a model that may have read hostile text, so it can never be a path like ../..
        raise ValueError(f"Invalid job name {job!r}: use the lowercase hyphenated folder name under workspace/.")
    return WORKSPACE / job


def _render_file(job: str) -> Path:
    return _job_dir(job) / "render.json"


def _spawn_render_watcher(job: str, video_id: str, chat_id: str) -> None:
    task = asyncio.create_task(_watch_render(job, video_id, chat_id))
    _background.add(task)  # strong reference: the event loop only keeps weak ones
    task.add_done_callback(_background.discard)


async def _watch_render(job: str, video_id: str, chat_id: str) -> None:
    message = "The render is still going after 15 minutes. Ask me to check on it again in a bit."
    deadline = time.monotonic() + RENDER_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        await asyncio.sleep(RENDER_POLL_SECONDS)
        state = json.loads(_render_file(job).read_text())
        if state["video_id"] != video_id or state["status"] != "rendering":  # a newer render replaced this one, or a check_video_status call already saw it end and told the user
            return
        data = await heygen_status(video_id)
        if data["status"] == "completed":
            _render_file(job).write_text(json.dumps({**state, "status": "completed", "video_url": data["video_url"]}))
            message = f"Your video is ready: {data['video_url']}\nThe link expires, so download the file if you want to keep it."
            break
        if data["status"] == "failed":
            _render_file(job).write_text(json.dumps({**state, "status": "failed"}))
            message = f"The render failed: {data['failure_message']}"
            break
    if chat_id:
        await post_as("producer", chat_id, message)


@mcp.tool()
def set_video_plan(job: str, script: str) -> str:
    """Save the spoken script for the video of a job to workspace/<job>/video_script.md. Does not start a render."""
    if error := script_length_error(script):
        return error
    path = _job_dir(job) / "video_script.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(script.strip() + "\n")
    return f"Script saved ({len(script.split())} words)."


@mcp.tool()
async def start_video_render(job: str, replace_existing: bool = False, chat_id: str = "") -> str:
    """Start rendering the saved script of a job into an avatar video. Costs credits: only call after the user has approved the current script. Pass replace_existing=true only if the user wants a new render although one already exists. Pass chat_id (the Discord channel the user is in) so the finished link is posted there automatically; leave it empty when the user is in the terminal."""
    render_file = _render_file(job)
    script = (_job_dir(job) / "video_script.md").read_text().strip()
    fingerprint = render_fingerprint(script)
    if render_file.exists() and not replace_existing:
        state = json.loads(render_file.read_text())
        if render_blocks_new_one(state["status"], state.get("fingerprint"), fingerprint):
            return render_exists_message(state["status"], state["video_id"])
    video_id = await heygen_start(script)
    render_file.write_text(json.dumps({"video_id": video_id, "status": "rendering", "video_url": "", "fingerprint": fingerprint}))
    _spawn_render_watcher(job, video_id, chat_id)
    if chat_id:
        return f"Render started (job {video_id}). It takes a few minutes, and the finished link is posted in the channel automatically."
    return f"Render started (job {video_id}). It takes a few minutes; use check_video_status to see when it is done."


@mcp.tool()
async def check_video_status(job: str) -> str:
    """Look up the status of the current render of a job."""
    render_file = _render_file(job)
    if not render_file.exists():
        return "No render has been started yet."
    state = json.loads(render_file.read_text())
    data = await heygen_status(state["video_id"])
    if data["status"] == "completed":
        render_file.write_text(json.dumps({**state, "status": "completed", "video_url": data["video_url"]}))
    elif data["status"] == "failed":
        render_file.write_text(json.dumps({**state, "status": "failed"}))
    return status_message(data)


if __name__ == "__main__":
    mcp.run()
