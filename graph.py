"""Graph wiring for the multi-agent content team.

    START -> lead --(next_agent)--> scout | content | producer | END
    scout, content and producer each hand back to lead when they finish.

Every agent is an LLM with its own model, persona prompt (personas/<persona>.md) and tools. One user message is one turn: lead routes, a specialist works and replies (its message is streamed to Discord as soon as the node finishes), lead hands off again or wraps up, and the turn ends at END. There is no interrupt(): the thread is persisted by the checkpointer, so the user's next message just starts the next turn with everything still in state. That is what lets the user talk to any agent at any time, not only at fixed approval points.
"""
from typing import Literal

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from llm import LLMS, agent_context, run_agent, system_prompt
from state import Persona, State
from tools import Workspace, content_tools, producer_tools, scout_tools


class Route(BaseModel):
    next: Literal["scout", "content", "producer", "finish"] = Field(description="Who acts next, or 'finish' to end this turn and wait for the user.")
    task: str = Field(description="A direct instruction for that specialist with everything they need; empty when next is 'finish'.")
    brief: str = Field(description="The updated one-paragraph brief for the job in progress; empty to keep the current brief.")
    new_job: bool = Field(description="True only when the user asks for a new, separate deliverable (for example another video or post) while an earlier job's drafts or video are still in the workspace. It clears those, but keeps the research. False for edits, questions and a first job.")
    message: str = Field(description="What to say to the user right now; empty to stay silent.")


MAX_REPLIES_PER_TURN = 2  # the longest legitimate case is content twice (write drafts, then record the pick); a third visit means lead and a specialist are going back and forth


def replies_this_turn(state: State, persona: str) -> int:
    count = 0
    for m in reversed(state["messages"]):
        if m["speaker"] == "user":
            break
        count += m["speaker"] == persona
    return count


async def lead(state: State) -> dict:
    router = LLMS["lead"].with_structured_output(Route)
    route = await router.ainvoke([system_prompt("lead"), HumanMessage(agent_context(state, "Fill in the routing form for the next step."))])
    if route.next != "finish" and replies_this_turn(state, route.next) >= MAX_REPLIES_PER_TURN:
        route.next, route.message = "finish", ""

    update: dict = {"next_agent": route.next, "task": route.task}
    if route.new_job:
        update.update(drafts=[], chosen_draft="", video_script="", video_job_id="", video_status="", video_url="")
    if route.brief:
        update["brief"] = route.brief
    if route.message:
        update["messages"] = [{"speaker": "lead", "content": route.message}]
    return update


def route_from_lead(state: State) -> str:
    return END if state["next_agent"] == "finish" else state["next_agent"]


async def _specialist(persona: Persona, state: State, config: RunnableConfig, make_tools) -> dict:
    ws = Workspace(state, config["configurable"]["thread_id"])
    reply = await run_agent(persona, state, state["task"], make_tools(ws))
    return {**ws.updates, "messages": [{"speaker": persona, "content": reply}]}


async def scout(state: State, config: RunnableConfig) -> dict:
    return await _specialist("scout", state, config, scout_tools)


async def content(state: State, config: RunnableConfig) -> dict:
    return await _specialist("content", state, config, content_tools)


async def producer(state: State, config: RunnableConfig) -> dict:
    return await _specialist("producer", state, config, producer_tools)


def build_graph(checkpointer):
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

    return graph.compile(checkpointer=checkpointer)
