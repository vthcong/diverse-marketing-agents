"""Shared graph state for the multi-agent content team."""
from __future__ import annotations

import operator
from typing import Optional, TypedDict

from typing_extensions import Annotated, Literal

Persona = Literal["lead", "scout", "content", "producer"]

Stage = Literal["new", "scouted", "draft_chosen", "complete"]

VideoTier = Literal["basic", "premium"]


class SpeakerMessage(TypedDict):
    """One agent's contribution, tagged with who said it.

    The Discord layer posts each entry under its `speaker`'s webhook identity rather than inferring who spoke from context.
    """

    speaker: Persona
    content: str


class State(TypedDict):
    request: str
    scout_findings: Optional[str]
    draft_options: Optional[list[str]]
    chosen_draft: Optional[str]
    video_tier: Optional[VideoTier]
    video_url: Optional[str]
    stage: Stage
    # Reducer appends rather than overwrites, so every node's output accumulates into one ordered trail across the whole run.
    messages: Annotated[list[SpeakerMessage], operator.add]