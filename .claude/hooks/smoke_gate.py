"""Stop hook: blocks Claude from ending its turn while scripts/smoke_test.py fails.

The test only runs when the code it covers changed since the last pass: a hash of every .py file, persona prompt and skill is saved in PASS_FILE after a pass, so a turn that only talked or edited docs ends instantly. A failing test never saves a hash, so it keeps blocking. Exit code 2 blocks the stop and its stderr is shown to Claude as the reason to keep going. Claude Code ends the turn anyway after 8 blocks in a row (the count resets when Claude calls a tool), so a test that can't be fixed can't loop forever; `stop_hook_active` in the input says a previous block is already being worked on, and this hook deliberately ignores it so Claude gets all 8 tries.
"""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PASS_FILE = Path(__file__).resolve().parent / ".smoke_pass"  # gitignored
TIMEOUT_SECONDS = 120
COVERED = ["*.py", "personas", ".claude/skills"]  # the smoke test loads persona prompts and skills too, so editing them can break it


def code_hash() -> str:
    files = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", *COVERED], cwd=ROOT, capture_output=True, text=True).stdout.split("\0")
    digest = hashlib.sha256()
    for name in sorted(filter(None, files)):
        path = ROOT / name
        if path.is_file():  # a file deleted in the working tree is still listed by --cached
            digest.update(name.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


current = code_hash()
if not PASS_FILE.exists() or PASS_FILE.read_text() != current:
    try:
        result = subprocess.run([sys.executable, "scripts/smoke_test.py"], cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        print(f"scripts/smoke_test.py did not finish within {TIMEOUT_SECONDS}s. Find what hangs before you stop.", file=sys.stderr)
        sys.exit(2)
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-15:])  # the traceback's end holds the real error; the top is warning noise
        print(f"scripts/smoke_test.py fails, so you can't stop yet. Fix the cause (the test itself is correct unless you changed the behaviour on purpose):\n{tail}", file=sys.stderr)
        sys.exit(2)
    PASS_FILE.write_text(current)
