"""The quality rules for agent-team runs, shared by task_completed_gate.py and teammate_idle_gate.py so the two hooks can't drift apart.

Neither hook payload names the job folder, so `current_job` picks the workspace folder whose brief.md is newest (the lead writes the brief first). A crash in a hook exits 1, which lets the task or idle through: these are quality checks, not safety checks, so they fail open (unlike render_gate.py).
"""
import re
from pathlib import Path

from paths import WORKSPACE
# Read the cap from heygen.py so there is one source of truth; importing it would load .env and httpx, which a hook doesn't need (same approach as the spoken-script skill's count_words.py)
MAX_WORDS = int(re.search(r"^MAX_VIDEO_WORDS = (\d+)", (Path(__file__).resolve().parent.parent / "servers" / "heygen.py").read_text(), re.M).group(1))

# teammate name -> (the file it reads, the file it must write)
FILES = {
    "scout": ("brief.md", "scout_findings.md"),
    "content": ("scout_findings.md", "drafts.md"),
    "producer": ("chosen.md", "video_script.md"),
}


def role(teammate: str | None) -> str | None:
    """The agent type behind a teammate name. Claude Code numbers a name that is already taken (producer-2), so drop a trailing -N."""
    return re.sub(r"-\d+$", "", teammate) if teammate else None


def current_job() -> Path | None:
    """The job folder the team is working on right now, or None when the workspace has no briefs."""
    briefs = list(WORKSPACE.glob("*/brief.md"))
    return max(briefs, key=lambda p: p.stat().st_mtime).parent if briefs else None


def completion_block_reason(teammate: str | None, job: Path) -> str | None:
    """Why this teammate's task can't be marked completed yet, or None when its output file passes."""
    teammate = role(teammate)
    if teammate not in FILES:  # the lead completing a task through TaskUpdate has no teammate name
        return None
    out = FILES[teammate][1]
    if not (job / out).exists():
        return f"Task not complete: {job.name}/{out} does not exist. Write it, then complete the task."
    text = (job / out).read_text()
    if teammate == "scout" and "http" not in text:
        return f"Task not complete: {out} cites no source URL. Every finding needs a link."
    if teammate == "content" and text.count("## Draft") != 3:
        return f"Task not complete: {out} must hold exactly 3 drafts under '## Draft N' headings, found {text.count('## Draft')}."
    if teammate == "producer" and len(text.split()) > MAX_WORDS:
        return f"Task not complete: {out} is {len(text.split())} words, over the {MAX_WORDS}-word cap. Shorten it."
    return None


def idle_block_reason(teammate: str, job: Path) -> str | None:
    """Why this teammate must not go idle yet, or None when idling is fine.

    Idle fires after EVERY teammate turn, including turns spent correctly waiting for upstream input, so it only blocks when the teammate has its input but has not written its output. A missing input, or a chosen.md that says "(none chosen)", means it is waiting, which is right.
    """
    teammate = role(teammate)
    if teammate not in FILES:
        return None
    src, out = FILES[teammate]
    has_input = (job / src).exists() and "(none chosen)" not in (job / src).read_text()
    if has_input and not (job / out).exists():
        return f"You have {job.name}/{src} but {out} is not written yet. Do your task and write {out} before going idle."
    return None
