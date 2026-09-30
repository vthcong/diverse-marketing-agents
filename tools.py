"""External services (Tavily, HeyGen) and the tools each specialist can call.

Tool factories close over a Workspace: reads see writes made earlier in the same agent turn, and writes are collected in ws.updates and returned from the node as its state update, so nothing mutates graph state behind LangGraph's back.
"""
import asyncio
import os
import time
from typing import Literal

import httpx
from dotenv import load_dotenv
from langchain_core.tools import BaseTool, tool
from langchain_tavily import TavilyExtract, TavilySearch

from state import State

load_dotenv()

HEYGEN_BASE = "https://api.heygen.com"
# HeyGen has no literal "tier" concept -- basic/premium is mapped to output resolution, using the one avatar/voice configured in .env for both.
HEYGEN_DIMENSIONS = {
    "basic": {"width": 1280, "height": 720},
    "premium": {"width": 1920, "height": 1080},
}
RENDER_POLL_SECONDS = 10
RENDER_TIMEOUT_SECONDS = 15 * 60

_locks: dict[str, asyncio.Lock] = {}


def thread_lock(thread_id: str) -> asyncio.Lock:
    """One lock per thread: a graph run and a background render finishing must never write the same thread's state at the same time."""
    return _locks.setdefault(thread_id, asyncio.Lock())


class Workspace:
    """One agent turn's read/write view of the shared state."""

    def __init__(self, state: State, thread_id: str):
        self.state = state
        self.thread_id = thread_id
        self.updates: dict = {}

    def get(self, key: str, default=None):
        return self.updates.get(key, self.state.get(key, default))

    def set(self, **values) -> None:
        self.updates.update(values)


def scout_tools(ws: Workspace) -> list[BaseTool]:
    @tool
    async def web_search(
        query: str,
        topic: Literal["general", "news"] = "general",
        depth: Literal["basic", "advanced"] = "basic",
        time_range: Literal["day", "week", "month", "year"] | None = None,
    ) -> str:
        """Search the web and return up to 5 results (title, URL, snippet). Use topic="news" and a time_range when recency matters; depth="advanced" only when basic results are thin."""
        search = TavilySearch(max_results=5, topic=topic, search_depth=depth, time_range=time_range)
        results = (await search.ainvoke({"query": query}))["results"]
        if not results:
            return "No results."
        return "\n\n".join(f"[{i}] {r['title']}\n{r['url']}\n{r['content'][:500]}" for i, r in enumerate(results, 1))

    @tool
    async def read_page(url: str, focus: str = "") -> str:
        """Read the main text of one web page (up to about 5000 characters). Optionally pass `focus`, what you're looking for, to prioritise relevant content."""
        response = await TavilyExtract(extract_depth="basic").ainvoke({"urls": [url], "query": focus or None})
        return response["results"][0]["raw_content"][:5000]

    @tool
    def save_findings(findings: str) -> str:
        """Store the research brief for the whole team. Replaces the previous brief, so merge in earlier findings that are still useful."""
        ws.set(findings=findings)
        return "Saved."

    return [web_search, read_page, save_findings]


def content_tools(ws: Workspace) -> list[BaseTool]:
    @tool
    def save_drafts(drafts: list[str]) -> str:
        """Replace the draft options in the shared workspace with this list (normally 3). Clears any previously chosen draft."""
        ws.set(drafts=drafts, chosen_draft="")
        return f"Saved {len(drafts)} draft(s)."

    @tool
    def choose_draft(number: int) -> str:
        """Lock in draft option `number` (1-based) as the final copy."""
        drafts = ws.get("drafts", [])
        if not 1 <= number <= len(drafts):
            return f"There is no draft {number}; there are {len(drafts)} draft(s)."
        ws.set(chosen_draft=drafts[number - 1])
        return f"Draft {number} is now the chosen copy."

    return [save_drafts, choose_draft]


async def heygen_start(script: str, tier: str) -> str:
    """Kicks off a render and returns HeyGen's video id straight away; it does not wait for the render."""
    payload = {
        "video_inputs": [
            {
                "character": {"type": "avatar", "avatar_id": os.environ["HEYGEN_AVATAR_ID"], "avatar_style": "normal"},
                "voice": {"type": "text", "input_text": script, "voice_id": os.environ["HEYGEN_VOICE_ID"]},
            }
        ],
        "dimension": HEYGEN_DIMENSIONS[tier],
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{HEYGEN_BASE}/v2/video/generate", headers={"X-Api-Key": os.environ["HEYGEN_API_KEY"]}, json=payload)
    resp.raise_for_status()
    return resp.json()["data"]["video_id"]


async def heygen_status(video_id: str) -> dict:
    """Returns HeyGen's status object: {"status": ..., "video_url": ..., "error": ...}."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{HEYGEN_BASE}/v1/video_status.get", params={"video_id": video_id}, headers={"X-Api-Key": os.environ["HEYGEN_API_KEY"]})
    resp.raise_for_status()
    return resp.json()["data"]


# Called as handler(thread_id, result) when a background render ends; result is {"status": "completed", "video_url": ...}, {"status": "failed", "error": ...} or {"status": "timeout"}.
_render_handler = None
_background: set[asyncio.Task] = set()


def set_render_handler(handler) -> None:
    global _render_handler
    _render_handler = handler


def _spawn_render_watcher(thread_id: str, video_id: str) -> None:
    task = asyncio.create_task(_watch_render(thread_id, video_id))
    _background.add(task)  # strong reference: the event loop only keeps weak ones
    task.add_done_callback(_background.discard)


async def _watch_render(thread_id: str, video_id: str) -> None:
    result: dict = {"status": "timeout"}
    deadline = time.monotonic() + RENDER_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        await asyncio.sleep(RENDER_POLL_SECONDS)
        data = await heygen_status(video_id)
        if data["status"] == "completed":
            result = {"status": "completed", "video_url": data["video_url"]}
            break
        if data["status"] == "failed":
            result = {"status": "failed", "error": data["error"]}
            break
    await _render_handler(thread_id, result)


def producer_tools(ws: Workspace) -> list[BaseTool]:
    @tool
    def set_video_plan(script: str, tier: Literal["basic", "premium"] = "basic") -> str:
        """Save the spoken script for the video and the quality tier ("basic" = 720p, "premium" = 1080p). Does not start a render."""
        ws.set(video_script=script, video_tier=tier)
        return f"Script saved ({len(script.split())} words, {tier} tier)."

    @tool
    async def start_video_render(replace_existing: bool = False) -> str:
        """Start rendering the saved script into an avatar video. Costs credits: only call after the user has approved the current script. Pass replace_existing=true only if the user wants a new render although one already exists."""
        if "video_script" in ws.updates:
            return "You wrote this script during this same turn, so the user hasn't seen it yet. Show it to them and wait for their approval first."
        if ws.get("video_status") in ("rendering", "completed") and not replace_existing:
            return f"A render is already {ws.get('video_status')} (job {ws.get('video_job_id')}). Only pass replace_existing=true if the user wants a new one."
        tier = ws.get("video_tier", "basic")
        video_id = await heygen_start(ws.get("video_script"), tier)
        ws.set(video_job_id=video_id, video_status="rendering", video_url="")
        _spawn_render_watcher(ws.thread_id, video_id)
        return f"Render started (job {video_id}, {tier} tier). It takes a few minutes, and the finished link is posted in the channel automatically."

    @tool
    async def check_video_status() -> str:
        """Look up the status of the current render."""
        if not (job := ws.get("video_job_id")):
            return "No render has been started yet."
        data = await heygen_status(job)
        if data["status"] == "completed":
            ws.set(video_status="completed", video_url=data["video_url"])
            return f"Completed: {data['video_url']}"
        if data["status"] == "failed":
            ws.set(video_status="failed")
            return f"The render failed: {data['error']}"
        return f"Still rendering (HeyGen status: {data['status']})."

    return [set_video_plan, start_video_render, check_video_status]