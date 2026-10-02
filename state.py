"""Shared graph state for the multi-agent content team."""
from __future__ import annotations
import operator
from typing import Literal, TypedDict
from typing_extensions import Annotated

Persona = Literal["lead", "scout", "content", "producer"]
Speaker = Literal["user", "lead", "scout", "content", "producer"]


class SpeakerMessage(TypedDict):
    speaker: Speaker
    content: str


class State(TypedDict, total=False):
    # Whole-thread transcript, user turns included. The reducer appends, so it accumulates for the life of the channel's thread; the Discord layer posts each agent message as its node finishes.
    messages: Annotated[list[SpeakerMessage], operator.add]

    # Lead's one-paragraph statement of the job in progress, shared with every specialist.
    brief: str

    # Lead's routing decision for the current hop.
    next_agent: Literal["scout", "content", "producer", "finish"]
    task: str

    # Shared workspace: written by the specialists' tools, read by everyone.
    findings: str
    drafts: list[str]
    chosen_draft: str
    video_script: str
    video_job_id: str
    video_status: str  # "rendering" | "completed" | "failed" | "timeout"
    video_url: str