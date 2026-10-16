"""PreToolUse hook for mcp__heygen__start_video_render, blocking with a JSON decision.

It always exits 0 and says what it wants on stdout. With "allow" the call would still go through the normal permission rules (the `ask` rule in settings.json), so allowing is done by printing nothing.
"""
import json
import sys

from approval import denial_reason

try:
    reason = denial_reason(json.load(sys.stdin))
except Exception as exc:  # a broken guard must fail closed
    reason = f"Render blocked: the render gate itself failed ({exc!r})."
if reason:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))
