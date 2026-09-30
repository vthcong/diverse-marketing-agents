"""LLM plumbing shared by every persona: one client per persona, the context each agent sees, and the tool-calling loop."""
import asyncio
from collections.abc import Sequence

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from personas import PERSONAS, llm_kwargs, load_skill, load_team
from state import Persona, State

MAX_TOOL_ROUNDS = 8
TRANSCRIPT_MESSAGES = 24
TRANSCRIPT_CHARS = 900
FINDINGS_CHARS = 6000

# Built at import, so a missing OPENAI_API_KEY fails right at startup.
LLMS: dict[Persona, ChatOpenAI] = {persona: ChatOpenAI(**llm_kwargs(persona)) for persona in PERSONAS}


def system_prompt(persona: Persona) -> SystemMessage:
    return SystemMessage(f"{load_team()}\n\n{load_skill(persona)}")


def roster() -> str:
    return "\n".join(f"- {p['username']}: {p['role']}" for p in PERSONAS.values())


def render_transcript(state: State) -> str:
    lines = []
    for m in state["messages"][-TRANSCRIPT_MESSAGES:]:
        text = m["content"] if len(m["content"]) <= TRANSCRIPT_CHARS else m["content"][:TRANSCRIPT_CHARS] + " [...]"
        lines.append(text if m["speaker"] == "user" else f"{PERSONAS[m['speaker']]['username']}: {text}")
    return "\n\n".join(lines)


def latest_user_message(state: State) -> str:
    return next(m["content"] for m in reversed(state["messages"]) if m["speaker"] == "user")


def render_workspace(state: State) -> str:
    findings = state.get("findings")
    drafts = state.get("drafts")
    if state.get("video_job_id") or state.get("video_script"):
        video = (
            f"script: {state.get('video_script') or '(none)'}\n"
            f"tier: {state.get('video_tier', 'basic')}\n"
            f"render status: {state.get('video_status') or 'not started'}\n"
            f"video url: {state.get('video_url') or '(none)'}"
        )
    else:
        video = "(none yet)"
    return "\n\n".join(
        [
            f"Brief: {state.get('brief') or '(no job started yet)'}",
            "Research findings:\n" + (findings[:FINDINGS_CHARS] if findings else "(none yet)"),
            "Draft options:\n" + ("\n".join(f"{i}. {d}" for i, d in enumerate(drafts, 1)) if drafts else "(none yet)"),
            f"Chosen draft: {state.get('chosen_draft') or '(none yet)'}",
            "Video:\n" + video,
        ]
    )


def agent_context(state: State, task: str) -> str:
    return "\n\n".join(
        [
            "## Team\n" + roster(),
            "## Shared workspace\n" + render_workspace(state),
            "## Conversation so far (oldest first)\n" + render_transcript(state),
            "## The user's latest message\n" + latest_user_message(state),
            "## Your task now\n" + task,
        ]
    )


async def run_agent(persona: Persona, state: State, task: str, tools: Sequence[BaseTool]) -> str:
    """Runs one persona's turn: shows it the team context and its task, lets it call its tools until it answers, and returns its reply text."""
    llm = LLMS[persona].bind_tools(list(tools))
    tools_by_name = {t.name: t for t in tools}
    convo = [system_prompt(persona), HumanMessage(agent_context(state, task))]

    for _ in range(MAX_TOOL_ROUNDS):
        ai = await llm.ainvoke(convo)
        convo.append(ai)
        if not ai.tool_calls:
            return ai.text.strip()
        results = await asyncio.gather(*(_call_tool(tools_by_name[c["name"]], c["args"]) for c in ai.tool_calls))
        convo.extend(ToolMessage(content=r, tool_call_id=c["id"]) for c, r in zip(ai.tool_calls, results))
    raise RuntimeError(f"{persona} was still calling tools after {MAX_TOOL_ROUNDS} rounds")


async def _call_tool(tool: BaseTool, args: dict) -> str:
    """The one error handler kept on purpose: a dead link or failed search is routine for a researcher, so the model gets the error as text and can adapt instead of the whole turn failing."""
    try:
        return str(await tool.ainvoke(args))
    except Exception as exc:
        return f"Tool error ({type(exc).__name__}): {exc}"