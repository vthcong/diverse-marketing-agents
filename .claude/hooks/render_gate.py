"""PreToolUse hook for mcp__heygen__start_video_render: blocks the render unless the user approved the job's script.

Exit code 2 is the only code that blocks a call, and its stderr is shown to Claude. Any other failure, such as an uncaught exception (exit 1), lets the call through, so every refusal below exits 2 explicitly.
"""
import json
import re
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent / "workspace"


def is_approved(job_dir: Path) -> bool:
    approved, script = job_dir / "approved", job_dir / "video_script.md"
    if not approved.exists() or not script.exists():
        return False
    return approved.stat().st_mtime >= script.stat().st_mtime  # a script edited after the approval needs a fresh yes


def deny(reason: str):
    print(reason, file=sys.stderr)
    sys.exit(2)


event = json.load(sys.stdin)
job = event["tool_input"].get("job", "")
if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", job):  # same rule as heygen_server._job_dir: the name comes from a model, so it can never be a path like ../..
    deny(f"Render blocked: {job!r} is not a valid job folder name.")
if not is_approved(WORKSPACE / job):
    deny(f"Render blocked: workspace/{job}/ has no current approval. Do not create the approval yourself. Report back to the lead, who must show the user the script and get a yes first.")
