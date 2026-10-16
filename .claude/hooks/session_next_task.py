"""SessionStart hook: tells Claude the learning path's next unchecked task, so a session opens knowing where to pick up.

Whatever a SessionStart hook prints to stdout is added to Claude's context. The task line is followed by its indented sub-bullets, up to the next task or heading.
"""
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "claude-code-learning-path.md"

lines = PATH.read_text().splitlines()
start = next((i for i, line in enumerate(lines) if line.startswith("- [ ]")), None)
if start is not None:
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith(("- [", "#"))), len(lines))
    task = "\n".join(lines[start:end]).rstrip()
    print(f"Next unchecked task in docs/claude-code-learning-path.md:\n{task}")
