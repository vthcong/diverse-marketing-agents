"""What the SDK bot (claude_bot.py) hands to the Claude Code agents: the HeyGen tools, the allow list, and the guards that hold even if the model is talked into something.

The HeyGen tools run in the bot's own process (`@tool` + `create_sdk_mcp_server`) instead of as the stdio server in mcp_servers/heygen_server.py. They are registered under the server name `heygen`, so the tool names are the same `mcp__heygen__*` the agent files in .claude/agents/ already list. The Discord channel is bound when the server is built, so the model never passes a chat id and cannot make a render announce itself in some other channel.

Permissions are decided in Python, in two places. `authorize` is the `can_use_tool` callback: Claude Code asks it before every tool call that is not already allowed, and it denies anything not on the list. It is used instead of dontAsk mode because .claude/settings.json has an `ask` rule for start_video_render, and dontAsk turns every `ask` into a refusal before anything else is consulted (tried: even a hook's allow does not get past it), so an approved render could never start. The PreToolUse hooks `render_gate` and `file_guard` are for the rules that must hold unconditionally: a hook also fires for tool calls made inside a subagent and for edits that a subagent's own permissionMode (acceptEdits in its agent file) would accept without asking `authorize`.
"""
import asyncio
import json
import re
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from claude_agent_sdk import HookMatcher, PermissionResultAllow, PermissionResultDeny, create_sdk_mcp_server, tool

from heygen import (
    heygen_start,
    heygen_status,
    render_blocks_new_one,
    render_exists_message,
    render_fingerprint,
    script_length_error,
    status_message,
)

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT / "workspace"

sys.path.insert(0, str(ROOT / ".claude" / "hooks"))  # approval.py holds the render approval rule shared with the Claude Code hooks, and that folder is not a package
from approval import denial_reason

RENDER_POLL_SECONDS = 60  # the same cadence as tools.py and mcp_servers/heygen_server.py
RENDER_TIMEOUT_SECONDS = 15 * 60

# Built-in tools that exist at all. There is no Bash: Discord messages are untrusted input, and a shell would turn one successful injection into code execution. The producer's word-count helper needs Bash, so file_guard enforces the word cap on the saved script instead.
BASE_TOOLS = ["Agent", "Read", "Write", "Edit", "Glob", "WebSearch", "WebFetch"]

# Everything authorize lets through. "Task" is the Agent tool's name inside the CLI. The three file tools are also checked against the folders below, and start_video_render is not here on purpose: it is allowed only by the approval check in authorize.
ALLOWED_TOOLS = {
    "Agent",
    "Task",
    "Read",
    "Write",
    "Edit",
    "Glob",
    "WebSearch",
    "WebFetch",
    "mcp__tavily__tavily_search",  # the scout's own inline Tavily server from its agent file
    "mcp__tavily__tavily_extract",
    "mcp__heygen__set_video_plan",
    "mcp__heygen__check_video_status",
}
READ_ROOTS = [WORKSPACE, ROOT / "personas", ROOT / ".claude" / "skills"]  # the job files, the role prompts every agent opens with, and the skills
WRITE_ROOTS = [WORKSPACE]

Notify = Callable[[str], Awaitable[None]]

_background: set[asyncio.Task] = set()


def _job_dir(job: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", job):  # the job name comes from a model that may have read hostile text, so it can never be a path like ../..
        raise ValueError(f"Invalid job name {job!r}: use the lowercase hyphenated folder name under workspace/.")
    return WORKSPACE / job


def _render_file(job: str) -> Path:
    return _job_dir(job) / "render.json"


def _text(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


async def watch_render(job: str, video_id: str, notify: Notify) -> None:
    """Polls HeyGen in the background and tells the channel how the render ended. Plain asyncio: it needs no agent, and it dies with the bot process like tools._watch_render does."""
    message = "The render is still going after 15 minutes. Ask me to check on it again in a bit."
    deadline = time.monotonic() + RENDER_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        await asyncio.sleep(RENDER_POLL_SECONDS)
        state = json.loads(_render_file(job).read_text())
        if state["video_id"] != video_id or state["status"] != "rendering":  # a newer render replaced this one, or a check_video_status call already saw it end and told the user
            return
        data = await heygen_status(video_id)
        if data["status"] == "completed":
            _render_file(job).write_text(json.dumps({**state, "status": "completed", "video_url": data["video_url"]}))
            message = f"Your video is ready: {data['video_url']}\nThe link expires, so download the file if you want to keep it."
            break
        if data["status"] == "failed":
            _render_file(job).write_text(json.dumps({**state, "status": "failed"}))
            message = f"The render failed: {data['failure_message']}"
            break
    await notify(message)


def heygen_tools(notify: Notify) -> list:
    """The three HeyGen tools, with the render watcher wired to notify. Split from heygen_server so a test can call the handlers directly."""

    @tool(
        "set_video_plan",
        "Save the spoken script for the video of a job to workspace/<job>/video_script.md. Does not start a render.",
        {"job": str, "script": str},
    )
    async def set_video_plan(args: dict) -> dict:
        if error := script_length_error(args["script"]):
            return _text(error)
        path = _job_dir(args["job"]) / "video_script.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["script"].strip() + "\n")
        return _text(f"Script saved ({len(args['script'].split())} words).")

    @tool(
        "start_video_render",
        "Start rendering the saved script of a job into an avatar video. Costs credits: only call after the user has approved the current script. Pass replace_existing=true only if the user wants a new render although one already exists. The finished link is posted in the channel automatically.",
        {
            "type": "object",
            "properties": {"job": {"type": "string"}, "replace_existing": {"type": "boolean"}},
            "required": ["job"],
        },
    )
    async def start_video_render(args: dict) -> dict:
        job = args["job"]
        if reason := render_problem({"job": job}):  # the hook and authorize have already run; checking again here keeps the rule true even if both are ever left out of the options
            raise ValueError(reason)
        script = (_job_dir(job) / "video_script.md").read_text().strip()
        if error := script_length_error(script):  # the script may have been edited after set_video_plan, and a render is the one step that costs money
            return _text(error)
        render_file = _render_file(job)
        fingerprint = render_fingerprint(script)
        if render_file.exists() and not args.get("replace_existing", False):
            state = json.loads(render_file.read_text())
            if render_blocks_new_one(state["status"], state.get("fingerprint"), fingerprint):
                return _text(render_exists_message(state["status"], state["video_id"]))
        video_id = await heygen_start(script)
        render_file.write_text(json.dumps({"video_id": video_id, "status": "rendering", "video_url": "", "fingerprint": fingerprint}))
        task = asyncio.create_task(watch_render(job, video_id, notify))
        _background.add(task)  # strong reference: the event loop only keeps weak ones
        task.add_done_callback(_background.discard)
        return _text(f"Render started (job {video_id}). It takes a few minutes, and the finished link is posted in the channel automatically.")

    @tool("check_video_status", "Look up the status of the current render of a job.", {"job": str})
    async def check_video_status(args: dict) -> dict:
        render_file = _render_file(args["job"])
        if not render_file.exists():
            return _text("No render has been started yet.")
        state = json.loads(render_file.read_text())
        data = await heygen_status(state["video_id"])
        if data["status"] == "completed":
            render_file.write_text(json.dumps({**state, "status": "completed", "video_url": data["video_url"]}))
        elif data["status"] == "failed":
            render_file.write_text(json.dumps({**state, "status": "failed"}))
        return _text(status_message(data))

    return [set_video_plan, start_video_render, check_video_status]


def heygen_server(notify: Notify):
    return create_sdk_mcp_server("heygen", tools=heygen_tools(notify))


def file_problem(tool_name: str, tool_input: dict) -> str | None:
    """Why this Read, Write or Edit is out of bounds, or None. Reads stay in READ_ROOTS, writes in workspace/, and a saved video script stays within the word cap."""
    try:
        path = (ROOT / tool_input["file_path"]).resolve()  # resolve() follows symlinks and removes .., so neither can lead out of the folder
        roots = READ_ROOTS if tool_name == "Read" else WRITE_ROOTS
        if not any(path.is_relative_to(root) for root in roots):
            return f"Blocked: {tool_name} may not touch {tool_input['file_path']}. Files live under workspace/."
        if tool_name == "Write" and path.name == "video_script.md" and (error := script_length_error(tool_input["content"])):
            return f"Blocked: {error}"
    except Exception as exc:  # a broken guard must fail closed; an exception in a hook callback would otherwise let the call through
        return f"Blocked: the file guard itself failed ({exc!r})."


def render_problem(tool_input: dict) -> str | None:
    """Why start_video_render must not run, or None when the user's approval of the current script is on file. The rule itself is .claude/hooks/approval.py, the same one the terminal hooks use."""
    try:
        return denial_reason({"tool_input": tool_input})
    except Exception as exc:  # a broken guard must fail closed
        return f"Render blocked: the render gate itself failed ({exc!r})."


async def authorize(tool_name: str, tool_input: dict, context) -> PermissionResultAllow | PermissionResultDeny:
    """The can_use_tool callback: allow what is on the list, deny the rest with a reason the model can read."""
    if tool_name == "mcp__heygen__start_video_render":
        reason = render_problem(tool_input)
    elif tool_name in ("Read", "Write", "Edit"):
        reason = file_problem(tool_name, tool_input)
    elif tool_name in ALLOWED_TOOLS:
        reason = None
    else:
        reason = f"{tool_name} is not on this bot's allow list."
    return PermissionResultDeny(message=reason) if reason else PermissionResultAllow()


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}


async def render_gate(event: dict, tool_use_id: str | None, context: dict) -> dict:
    """PreToolUse hook: no render without the user's approval, whatever any permission mode or rule says."""
    reason = render_problem(event["tool_input"])
    return _deny(reason) if reason else {}


async def file_guard(event: dict, tool_use_id: str | None, context: dict) -> dict:
    """PreToolUse hook for the file tools. It sees subagent calls too, and implicitly allowed reads, so it holds where authorize is never asked."""
    reason = file_problem(event["tool_name"], event["tool_input"])
    return _deny(reason) if reason else {}


HOOKS = {
    "PreToolUse": [
        HookMatcher(matcher="mcp__heygen__start_video_render", hooks=[render_gate]),
        HookMatcher(matcher="Read|Write|Edit", hooks=[file_guard]),
    ],
}
