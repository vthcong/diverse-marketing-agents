"""MCP server that exposes the HeyGen video tools to Claude Code.

State lives in files under workspace/<job>/: video_script.md is the spoken script and render.json holds the HeyGen job id and last known status. The render approval gate is deliberately not here: it is a permission rule (5.2) and a hook (6.1).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # a script run by path only has its own folder on sys.path, so the project root must be added to import heygen.py

from mcp.server.fastmcp import FastMCP

from heygen import heygen_start, heygen_status, render_exists_message, script_length_error, status_message

WORKSPACE = ROOT / "workspace"

mcp = FastMCP("heygen")


def _job_dir(job: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", job):  # the job name comes from a model that may have read hostile text, so it can never be a path like ../..
        raise ValueError(f"Invalid job name {job!r}: use the lowercase hyphenated folder name under workspace/.")
    return WORKSPACE / job


def _render_file(job: str) -> Path:
    return _job_dir(job) / "render.json"


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
async def start_video_render(job: str, replace_existing: bool = False) -> str:
    """Start rendering the saved script of a job into an avatar video. Costs credits: only call after the user has approved the current script. Pass replace_existing=true only if the user wants a new render although one already exists."""
    render_file = _render_file(job)
    if render_file.exists() and not replace_existing:
        state = json.loads(render_file.read_text())
        if state["status"] in ("rendering", "completed"):
            return render_exists_message(state["status"], state["video_id"])
    script = (_job_dir(job) / "video_script.md").read_text().strip()
    video_id = await heygen_start(script)
    render_file.write_text(json.dumps({"video_id": video_id, "status": "rendering", "video_url": ""}))
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
