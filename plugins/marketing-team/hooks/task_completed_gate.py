"""TaskCompleted hook: a teammate's task can't be marked done until its output file passes team_gate.completion_block_reason.

Exit code 2 refuses the completion and its stderr goes back to the model as feedback.
"""
import json
import sys

from team_gate import completion_block_reason, current_job

event = json.load(sys.stdin)
job = current_job()
reason = job and completion_block_reason(event.get("teammate_name"), job)  # teammate_name may be absent
if reason:
    print(reason, file=sys.stderr)
    sys.exit(2)
