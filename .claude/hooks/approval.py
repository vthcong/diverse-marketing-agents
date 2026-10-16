"""The render approval rule, shared by render_gate.py (exit code 2) and render_gate_json.py (JSON decision), so the two ways of blocking can't drift apart."""
import re
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent / "workspace"


def denial_reason(event: dict) -> str | None:
    """Why this start_video_render call must be blocked, or None when the user's approval is current."""
    job = event["tool_input"].get("job", "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", job):  # same rule as heygen_server._job_dir: the name comes from a model, so it can never be a path like ../..
        return f"Render blocked: {job!r} is not a valid job folder name."
    approved, script = WORKSPACE / job / "approved", WORKSPACE / job / "video_script.md"
    if approved.exists() and script.exists() and approved.stat().st_mtime >= script.stat().st_mtime:  # a script edited after the approval needs a fresh yes
        return None
    return f"Render blocked: workspace/{job}/ has no current approval. Do not create the approval yourself. Report back to the lead, who must show the user the script and get a yes first."
