"""PostToolUse hook for Edit|Write: checks that an edited .py file still compiles and feeds the error back to Claude.

The edit has already happened by the time this runs, so exit code 2 cannot undo it; its stderr is shown to Claude so it fixes the file in the same turn. Any other exit code is only logged, so a clean file just exits 0.
"""
import json
import os
import sys

path = json.load(sys.stdin)["tool_input"].get("file_path", "")
if path.endswith(".py") and os.path.exists(path):
    try:
        compile(open(path).read(), path, "exec")  # the same grammar check as `python -m py_compile`, without writing a .pyc
    except SyntaxError as exc:
        print(f"Syntax error in {path} after your edit. Fix it now: {exc.msg} (line {exc.lineno}): {exc.text}", file=sys.stderr)
        sys.exit(2)
