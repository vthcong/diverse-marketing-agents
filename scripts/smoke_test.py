"""Mocked end-to-end smoke test: drives the whole team through discord_bot.handle_turn with every external service faked, so only the models' decisions are scripted.

Command:
cd /Users/mac/Documents/Important/Self-study/agentic/diverse_marketing_agents
/opt/miniconda3/envs/langchain/bin/python scripts/smoke_test.py
"""
import asyncio
import itertools
import json
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from unittest import mock

# Set before any project import: llm.py builds its clients at import and discord_bot.py reads the token at import.
os.environ["OPENAI_API_KEY"] = "test"
os.environ["DISCORD_BOT_TOKEN"] = "test"

import dotenv

dotenv.load_dotenv = lambda *args, **kwargs: False  # tools.py and personas.py call this at import; the test must never read the real .env
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

import discord_bot
import graph
import llm
import tools


# --- Step builders: each one is what a model "says" on one request. ---

_call_ids = itertools.count(1)


def say(text: str) -> dict:
    """A final answer with no tool calls."""
    return {"content": text}


def call(*calls: tuple[str, dict]) -> dict:
    """One or more tool calls in the same round, as (tool name, arguments) pairs."""
    return {"content": None, "tool_calls": [{"id": f"call_{next(_call_ids)}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}} for name, args in calls]}


def route(next: str, task: str = "", brief: str = "", new_job: bool = False, message: str = "") -> dict:
    """Lead's structured answer: the fields of graph.Route."""
    return {"next": next, "task": task, "brief": brief, "new_job": new_job, "message": message}


# --- The scripts: one list per persona, consumed one step per model request, in order. ---

# Turn 1 is the request "write a hiring post and a video", turn 2 is the approval. Lead decides, in order: research, drafts, pick, video script, stop for approval; then on approval the render, then stop. The specialists below are written to match that order: scout 1 visit, content 2 visits (drafts, then the pick), producer 2 visits (script, then render).
LEAD_STEPS = [
    route("scout", task="Research hiring trends for backend engineers.", brief="Hiring post and short video for a backend engineer role."),
    route("content", task="Write 3 draft options."),
    route("content", task="Lock in draft 2."),
    route("producer", task="Write the video script."),
    route("finish", message="The script is ready. Approve it and I'll render."),
    route("producer", task="Render the approved script."),
    route("finish"),
]

VIDEO_SCRIPT = "We are hiring a backend engineer. Join a small team shipping real products. Apply today."

SCRIPT = {
    "lead": LEAD_STEPS,
    "scout": [
        call(("web_search", {"query": "backend engineer hiring trends"}), ("read_page", {"url": "https://example.test/hiring"})),
        call(("save_findings", {"findings": "Engineers want remote work and clear growth. Source: https://example.test/hiring"})),
        say("Research saved."),
    ],
    "content": [
        call(("save_drafts", {"drafts": ["Draft A", "Draft B", "Draft C"]})),
        say("Three drafts are saved."),
        call(("choose_draft", {"number": 2})),
        say("Locked in draft 2."),
    ],
    "producer": [
        call(("set_video_plan", {"script": VIDEO_SCRIPT})),
        call(("start_video_render", {})),  # too early on purpose: the script was written this same turn, so the gate in tools.py must refuse
        say("The script is ready. Approve it and I'll render."),
        call(("start_video_render", {})),
        say("Render started."),
    ],
}


# --- Fake OpenAI: one MockTransport handler per persona that answers from that persona's script. ---

def completion(message: dict) -> httpx.Response:
    finish = "tool_calls" if message.get("tool_calls") else "stop"
    body = {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "created": 0,
        "model": "fake",
        "choices": [{"index": 0, "finish_reason": finish, "message": {"role": "assistant", "refusal": None, **message}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    return httpx.Response(200, json=body)


remaining = {persona: list(steps) for persona, steps in SCRIPT.items()}


def fake_openai(persona: str):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if not remaining[persona]:
            raise RuntimeError(f"{persona} made more model requests than its script has steps")
        step = remaining[persona].pop(0)
        if persona != "lead":
            return completion(step)
        if "response_format" in body:
            return completion({"content": json.dumps(step)})
        return completion(call((body["tools"][0]["function"]["name"], step)))

    return handler


# --- Fake Discord, Tavily and HeyGen. ---

class FakeHook:
    def __init__(self):
        self.posts: list[tuple[str, str]] = []

    async def send(self, content, username, avatar_url, allowed_mentions):
        self.posts.append((username, content))


class FakeChannel:
    id = 4242

    @asynccontextmanager
    async def typing(self):
        yield


class FakeSearch:
    def __init__(self, **kwargs):
        pass

    async def ainvoke(self, inputs):
        return {"results": [{"title": "Hiring trends", "url": "https://example.test/hiring", "content": "Remote work and growth matter most."}]}


class FakeExtract:
    def __init__(self, **kwargs):
        pass

    async def ainvoke(self, inputs):
        return {"results": [{"raw_content": "Full page text about hiring backend engineers."}]}


started: list[str] = []


async def fake_heygen_start(script: str) -> str:
    started.append(script)
    return "vid_1"


async def fake_heygen_status(video_id: str) -> dict:
    return {"status": "completed", "video_url": "https://example.test/vid_1.mp4"}


async def main() -> None:
    hook, channel = FakeHook(), FakeChannel()
    discord_bot.webhooks[channel.id] = hook
    config = {"configurable": {"thread_id": str(channel.id)}}
    for persona in SCRIPT:
        llm.LLMS[persona] = ChatOpenAI(model=llm.PERSONAS[persona]["model"], api_key="x", max_retries=0, http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(fake_openai(persona))))

    patches = mock.patch.multiple(tools, TavilySearch=FakeSearch, TavilyExtract=FakeExtract, heygen_start=fake_heygen_start, heygen_status=fake_heygen_status, RENDER_POLL_SECONDS=0)
    with patches, mock.patch.object(discord_bot.client, "get_channel", return_value=channel), tempfile.TemporaryDirectory() as tmp:
        async with AsyncSqliteSaver.from_conn_string(str(Path(tmp) / "smoke.sqlite")) as saver:
            discord_bot.app = graph.build_graph(saver)
            tools.set_render_handler(discord_bot.on_render_finished)

            await discord_bot.handle_turn(channel, "Dana: Write a hiring post for a backend engineer and make a short video.")
            state = (await discord_bot.app.aget_state(config)).values
            assert state["findings"], "scout saved no findings"
            assert state["drafts"] == ["Draft A", "Draft B", "Draft C"], f"unexpected drafts: {state['drafts']}"
            assert state["chosen_draft"] == "Draft B", f"unexpected chosen draft: {state['chosen_draft']}"
            assert state["video_script"] == VIDEO_SCRIPT, "producer did not save the script"
            assert len(state["video_script"].split()) <= tools.MAX_VIDEO_WORDS, "script is over the word cap"
            assert not started, "a render started in the same turn the script was written: the approval gate is broken"

            await discord_bot.handle_turn(channel, "Dana: Approved, render it.")
            await asyncio.gather(*tools._background)
            state = (await discord_bot.app.aget_state(config)).values
            assert started == [VIDEO_SCRIPT], f"expected exactly one render of the approved script, got {started}"
            assert state["video_status"] == "completed", f"video status is {state['video_status']}"
            assert state["video_url"] == "https://example.test/vid_1.mp4", f"unexpected video url: {state['video_url']}"
            assert hook.posts[-1] == ("Paul", "The video is ready: https://example.test/vid_1.mp4"), f"last post was {hook.posts[-1]}"

    unused = {persona: len(steps) for persona, steps in remaining.items() if steps}
    assert not unused, f"script steps never used, so the graph took a different path than scripted: {unused}"
    print(f"SMOKE TEST PASSED: {len(hook.posts)} messages posted by {sorted({name for name, _ in hook.posts})}")


if __name__ == "__main__":
    asyncio.run(main())
