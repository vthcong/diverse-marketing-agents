"""TeammateIdle hook: keeps a teammate working when team_gate.idle_block_reason says it is idling without having done its work.

Exit code 2 stops the idle and its stderr goes to the teammate as feedback. A teammate that is truly stuck would be sent back forever, so each teammate is blocked at most MAX_BLOCKS times per session; after that it may idle and the lead sees the idle notice. The counts live in STATE_FILE, reset by a new session id.
"""
import json
import os
import sys

from paths import state_dir
from team_gate import current_job, idle_block_reason

STATE_FILE = state_dir() / ".teammate_idle.json"
MAX_BLOCKS = 2


def load_state(session_id: str) -> dict:
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:  # a torn write from a concurrent hook; the counts are disposable, so start over
            state = {}
        if state.get("session_id") == session_id:
            return state
    return {"session_id": session_id, "blocks": {}}


def save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(f".{os.getpid()}.tmp")  # per-process name so two hooks never share a temp file
    tmp.write_text(json.dumps(state))
    os.replace(tmp, STATE_FILE)  # atomic swap: readers see the old file or the new one, never a mix


event = json.load(sys.stdin)
teammate = event["teammate_name"]
job = current_job()
reason = job and idle_block_reason(teammate, job)
if reason:
    state = load_state(event["session_id"])
    if state["blocks"].get(teammate, 0) < MAX_BLOCKS:
        state["blocks"][teammate] = state["blocks"].get(teammate, 0) + 1
        save_state(state)
        print(reason, file=sys.stderr)
        sys.exit(2)
