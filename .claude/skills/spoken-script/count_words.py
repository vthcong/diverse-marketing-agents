"""Check a spoken video script against the word cap before it is saved: count_words.py "script text" (or pipe the script on stdin)."""
import re
import sys
from pathlib import Path

# Read the cap from heygen.py so there is one source of truth; importing it would pull in httpx and python-dotenv, which the system python may not have
MAX_VIDEO_WORDS = int(re.search(r"^MAX_VIDEO_WORDS = (\d+)", (Path(__file__).resolve().parents[3] / "heygen.py").read_text(), re.M).group(1))
SECONDS_PER_WORD = 0.5

# What an avatar can't speak: pattern -> label
UNSPEAKABLE = {
    r"#\w": "hashtag",
    r"https?://|www\.": "URL",
    r"[*_`\[\]>]": "markdown character",
    r"[\U0001F000-\U0001FFFF☀-➿]": "emoji",
}

script = " ".join(sys.argv[1:]) or sys.stdin.read()
words = len(script.split())  # same count as tools.py
problems = [f"contains a {label}" for pattern, label in UNSPEAKABLE.items() if re.search(pattern, script)]
if words > MAX_VIDEO_WORDS:
    problems.append(f"{words - MAX_VIDEO_WORDS} words over the {MAX_VIDEO_WORDS}-word cap")

print(f"{words}/{MAX_VIDEO_WORDS} words, about {words * SECONDS_PER_WORD:.0f} seconds")
for problem in problems:
    print(f"PROBLEM: {problem}")
sys.exit(1 if problems else 0)
