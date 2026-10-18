"""Caps how many times in a row Lead may run the same specialist; the Claude Code version of a per-turn reply cap.

One script handles three events, told apart by `hook_event_name`, and they share a tiny state file (STATE_FILE):
- SubagentStop: a specialist finished, so count it. A different specialist than last time restarts the count at 1.
- PreToolUse on the Agent tool: Lead is about to start a specialist. If it is the same one that just finished MAX_CONSECUTIVE times, exit 2 denies the call and its stderr tells Lead to move on. SubagentStop cannot do this itself: it fires after a run and its exit 2 only makes that subagent keep working.
- UserPromptSubmit: a new user message is a new turn, so the count starts over.

It does not catch an A, B, A, B ping-pong, and a crash here exits 1, which lets the call through. Concurrent hooks can still lose an update (read, change, write), so a count may be off by one, but the file is never left corrupt.
"""
import json
import os
import sys

from paths import state_dir

STATE_FILE = state_dir() / ".loop_cap.json"
MAX_CONSECUTIVE = 2  # the third run in a row is the one that gets blocked


def load_state(session_id: str) -> dict:
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:  # a torn write from a concurrent hook; the count is disposable, so start over
            state = {}
        if state.get("session_id") == session_id:
            return state
    return {"session_id": session_id, "agent": None, "count": 0}


def save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(f".{os.getpid()}.tmp")  # per-process name so two hooks never share a temp file
    tmp.write_text(json.dumps(state))
    os.replace(tmp, STATE_FILE)  # atomic swap: readers see the old file or the new one, never a mix


event = json.load(sys.stdin)
state = load_state(event["session_id"])

if event["hook_event_name"] == "UserPromptSubmit":
    save_state({**state, "agent": None, "count": 0})
elif event["hook_event_name"] == "SubagentStop":
    state["count"] = state["count"] + 1 if state["agent"] == event["agent_type"] else 1
    state["agent"] = event["agent_type"]
    save_state(state)
elif event["hook_event_name"] == "PreToolUse":
    requested = event["tool_input"]["subagent_type"]
    if requested == state["agent"] and state["count"] >= MAX_CONSECUTIVE:
        print(f"Loop cap: {requested} already ran {state['count']} times in a row this turn. Don't call {requested} again; hand the job to a different specialist, or end your turn and tell the user what is still missing.", file=sys.stderr)
        sys.exit(2)
