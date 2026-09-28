"""Graph wiring for the multi-agent content team.

Real agent logic:
  - scout: Tavily web search for angles/trends relevant to the request.
  - content: OpenAI drafts 3 caption options from the request + scout's findings, then pauses for the user to pick one.
  - producer: HeyGen renders an avatar video reading the chosen draft, then pauses for approval.

    START -> lead --(routes on stage)--> scout | content | producer | END
    scout, content, producer each report back to lead when done.

Checkpointer: AsyncSqliteSaver, persisted to checkpoints.sqlite, so a paused thread (mid-interrupt)
survives a bot restart instead of being silently dropped. build_graph() is async because opening
that connection requires one; callers must `await build_graph()` from within an event loop.
"""
import os
import time

import requests
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from state import State

load_dotenv()

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

HEYGEN_API_KEY = os.environ.get("HEYGEN_API_KEY")
HEYGEN_AVATAR_ID = os.environ.get("HEYGEN_AVATAR_ID")
HEYGEN_VOICE_ID = os.environ.get("HEYGEN_VOICE_ID")

# HeyGen has no literal "tier" concept -- basic/premium is mapped to output resolution here, using the one avatar/voice configured via env vars for both.
HEYGEN_DIMENSIONS = {
    "basic": {"width": 1280, "height": 720},
    "premium": {"width": 1920, "height": 1080},
}


def lead(state: State) -> dict:
    """Router + occasional narrator. Doesn't call an LLM in the MVP — there's nothing to decide yet that state["stage"] doesn't already tell us."""
    stage = state["stage"]
    if stage == "new":
        return {
            "messages": [
                {
                    "speaker": "lead",
                    "content": f"Got it — let's work on: {state['request']}. Bringing in Scout first.",
                }
            ]
        }
    if stage == "complete":
        return {
            "messages": [
                {"speaker": "lead", "content": "All done — this one's ready to publish!"}
            ]
        }
    return {}  # "scouted" / "draft_chosen": just route onward, nothing to say


def route_from_lead(state: State) -> str:
    stage = state["stage"]
    if stage == "new":
        return "scout"
    if stage == "scouted":
        return "content"
    if stage == "draft_chosen":
        return "producer"
    return END  # "complete"


def _search_findings(request: str) -> str:
    """Runs a Tavily search for the request topic and formats a short findings summary."""
    tool = TavilySearch(max_results=5, topic="general")
    response = tool.invoke({"query": request})
    results = response.get("results", []) if isinstance(response, dict) else []
    if not results:
        return "No notable findings from search."
    return "\n".join(f"- {r.get('title', 'untitled')}: {r.get('content', '')[:200]}" for r in results)


def scout(state: State) -> dict:
    """Tavily search for angles/trends relevant to the request."""
    findings = _search_findings(state["request"])
    return {
        "stage": "scouted",
        "scout_findings": findings,
        "messages": [
            {"speaker": "scout", "content": f"Found some angles to consider:\n{findings}"}
        ],
    }


def _parse_choice(user_reply: str, num_options: int) -> int:
    """Best-effort parse of '1'/'2'/'3' -> 0-based index. Defaults to the first option if the reply doesn't parse — good enough for the MVP."""
    try:
        index = int(user_reply.strip()) - 1
        if 0 <= index < num_options:
            return index
    except (ValueError, AttributeError):
        pass
    return 0


_draft_llm: ChatOpenAI | None = None


def _get_draft_llm() -> ChatOpenAI:
    """Built lazily (not at import time) so graph.py can still be imported before OPENAI_API_KEY is set."""
    global _draft_llm
    if _draft_llm is None:
        _draft_llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0.7)
    return _draft_llm


def _generate_drafts(request: str, scout_findings: str | None) -> list[str]:
    """Asks the LLM for 3 distinct draft options based on the request + Scout's findings."""
    prompt = (
        "You are a marketing copywriter. Write exactly 3 short, distinct social media post drafts "
        f"for this request: {request}\n\n"
        f"Relevant research/context:\n{scout_findings or 'none'}\n\n"
        "Reply with exactly 3 drafts, one per line, no numbering, no extra commentary."
    )
    response = _get_draft_llm().invoke(prompt)
    lines = [line.strip() for line in response.content.strip().split("\n") if line.strip()]
    if len(lines) < 3:
        lines += ["(model returned fewer than 3 drafts)"] * (3 - len(lines))
    return lines[:3]


def content(state: State) -> dict:
    """LLM-drafted options + a real interrupt: pauses the graph to surface the 3 options, then waits for the user's pick.

    Drafts are cached into state on first generation and reused on resume, so re-running this
    function from the top (as interrupt() causes) doesn't re-call the LLM or change the options
    the user is picking between.
    """
    drafts = state.get("draft_options") or _generate_drafts(state["request"], state.get("scout_findings"))
    numbered = "\n".join(f"{i + 1}. {d}" for i, d in enumerate(drafts))
    user_reply = interrupt(
        {
            "speaker": "content",
            "content": f"Here are 3 directions:\n{numbered}\n\nReply with 1, 2, or 3.",
        }
    )
    chosen = drafts[_parse_choice(user_reply, len(drafts))]
    return {
        "draft_options": drafts,
        "chosen_draft": chosen,
        "stage": "draft_chosen",
        "messages": [{"speaker": "content", "content": f"Great — going with: {chosen}"}],
    }


def _generate_video(script: str, tier: str) -> str:
    """Calls HeyGen to render an avatar video reading `script`, polls until done, returns the video URL."""
    if not (HEYGEN_API_KEY and HEYGEN_AVATAR_ID and HEYGEN_VOICE_ID):
        raise RuntimeError(
            "HEYGEN_API_KEY, HEYGEN_AVATAR_ID, and HEYGEN_VOICE_ID must all be set in .env to generate video."
        )
    dimension = HEYGEN_DIMENSIONS.get(tier, HEYGEN_DIMENSIONS["basic"])
    headers = {"X-Api-Key": HEYGEN_API_KEY, "Content-Type": "application/json"}

    generate_resp = requests.post(
        "https://api.heygen.com/v2/video/generate",
        headers=headers,
        json={
            "video_inputs": [
                {
                    "character": {"type": "avatar", "avatar_id": HEYGEN_AVATAR_ID, "avatar_style": "normal"},
                    "voice": {"type": "text", "input_text": script, "voice_id": HEYGEN_VOICE_ID},
                }
            ],
            "dimension": dimension,
        },
        timeout=30,
    )
    generate_resp.raise_for_status()
    video_id = generate_resp.json()["data"]["video_id"]

    status_url = f"https://api.heygen.com/v1/video_status.get?video_id={video_id}"
    deadline = time.monotonic() + 600  # HeyGen renders typically take 1-5 min; give it 10.
    while time.monotonic() < deadline:
        status_resp = requests.get(status_url, headers={"X-Api-Key": HEYGEN_API_KEY}, timeout=30)
        status_resp.raise_for_status()
        data = status_resp.json()["data"]
        if data["status"] == "completed":
            return data["video_url"]
        if data["status"] == "failed":
            raise RuntimeError(f"HeyGen video generation failed: {data.get('error')}")
        time.sleep(10)
    raise TimeoutError("HeyGen video generation timed out after 10 minutes.")


def producer(state: State) -> dict:
    """HeyGen video generation + a real interrupt: pauses to surface the finished video, then waits for approval.

    video_url is cached into state on first generation and reused on resume, for the same
    re-run-from-the-top reason as content()'s draft caching — otherwise a resume would trigger
    a second, unnecessary (and costly) HeyGen render.
    """
    tier = state.get("video_tier") or "basic"
    video_url = state.get("video_url") or _generate_video(state["chosen_draft"], tier)
    user_reply = interrupt(
        {
            "speaker": "producer",
            "content": f"Video ready ({tier} tier): {video_url}\n\nReply 'approve' or say what to change.",
        }
    )
    return {
        "video_tier": tier,
        "video_url": video_url,
        "stage": "complete",
        "messages": [{"speaker": "producer", "content": f"Got it — noted: {user_reply}"}],
    }


_checkpointer_cm = None
_checkpointer: AsyncSqliteSaver | None = None


async def _get_checkpointer() -> AsyncSqliteSaver:
    """Opens (once per process) a persistent AsyncSqliteSaver backed by a local file, kept open for
    the process's lifetime so paused threads survive a restart. The context manager is entered
    manually (not via `async with`) because the connection must outlive this function call."""
    global _checkpointer_cm, _checkpointer
    if _checkpointer is None:
        _checkpointer_cm = AsyncSqliteSaver.from_conn_string("checkpoints.sqlite")
        _checkpointer = await _checkpointer_cm.__aenter__()
        await _checkpointer.setup()
    return _checkpointer


async def build_graph():
    graph = StateGraph(State)
    graph.add_node("lead", lead)
    graph.add_node("scout", scout)
    graph.add_node("content", content)
    graph.add_node("producer", producer)

    graph.add_edge(START, "lead")
    graph.add_conditional_edges(
        "lead",
        route_from_lead,
        {"scout": "scout", "content": "content", "producer": "producer", END: END},
    )
    graph.add_edge("scout", "lead")
    graph.add_edge("content", "lead")
    graph.add_edge("producer", "lead")

    checkpointer = await _get_checkpointer()
    return graph.compile(checkpointer=checkpointer)
