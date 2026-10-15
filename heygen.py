"""HeyGen's API and the rules around it, shared by the Discord bot (tools.py) and the MCP server (mcp_servers/heygen_server.py).

Keep this module free of LangChain, LangGraph and MCP imports so both sides can depend on it without depending on each other.
"""
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

HEYGEN_BASE = "https://api.heygen.com"
HEYGEN_RESOLUTION = "720p"  # every video is rendered at 720p
MAX_VIDEO_WORDS = 50  # HeyGen has no max-duration setting, so the script length is the only cap; at ~0.5 s per word this is about 25 seconds


async def heygen_start(script: str) -> str:
    """Kicks off a render and returns HeyGen's video id straight away; it does not wait for the render."""
    payload = {
        "type": "avatar",
        "avatar_id": os.environ["HEYGEN_AVATAR_ID"],
        "voice_id": os.environ["HEYGEN_VOICE_ID"],
        "script": script,
        "resolution": HEYGEN_RESOLUTION,
        "aspect_ratio": "9:16",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{HEYGEN_BASE}/v3/videos",
            headers={"x-api-key": os.environ["HEYGEN_API_KEY"]},
            json=payload
        )
    resp.raise_for_status()
    return resp.json()["data"]["video_id"]


async def heygen_status(video_id: str) -> dict:
    """Returns HeyGen's video object: status is pending/processing/completed/failed, plus video_url when completed and failure_message when failed."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{HEYGEN_BASE}/v3/videos/{video_id}",
            headers={"x-api-key": os.environ["HEYGEN_API_KEY"]}
        )
    resp.raise_for_status()
    return resp.json()["data"]


def script_length_error(script: str) -> str | None:
    """The refusal text when the script is over the cap, otherwise None."""
    if (words := len(script.split())) > MAX_VIDEO_WORDS:
        return f"Not saved: the script is {words} words, over the {MAX_VIDEO_WORDS}-word limit. Shorten it and save it again."


def render_exists_message(status: str, video_id: str) -> str:
    return f"A render is already {status} (job {video_id}). Only pass replace_existing=true if the user wants a new one."


def status_message(data: dict) -> str:
    """The text for a HeyGen video object from heygen_status."""
    if data["status"] == "completed":
        return f"Completed: {data['video_url']}"
    if data["status"] == "failed":
        return f"The render failed: {data['failure_message']}"
    return f"Still rendering (HeyGen status: {data['status']})."
