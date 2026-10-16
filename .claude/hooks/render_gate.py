"""PreToolUse hook for mcp__heygen__start_video_render, blocking with exit code 2.

Exit code 2 is the only code that blocks a call, and its stderr is shown to Claude. Any other failure, such as an uncaught exception (exit 1), lets the call through, so a crash here is turned into a block too.
"""
import json
import sys

from approval import denial_reason

try:
    reason = denial_reason(json.load(sys.stdin))
except Exception as exc:  # a broken guard must fail closed
    reason = f"Render blocked: the render gate itself failed ({exc!r})."
if reason:
    print(reason, file=sys.stderr)
    sys.exit(2)
