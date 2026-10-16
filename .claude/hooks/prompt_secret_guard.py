"""UserPromptSubmit hook: refuses a prompt that contains a credential.

A blocked prompt is erased and never reaches Claude or the transcript; the user sees only the reason. The reason names the kind of secret and never repeats it. It is a tripwire for pasted keys, not a scanner: it only knows the shapes below.
"""
import json
import re
import sys

SECRET_PATTERNS = {
    "an Anthropic API key": r"sk-ant-[A-Za-z0-9_-]{20,}",
    "an OpenAI API key": r"sk-(?!ant-)(?:proj-)?[A-Za-z0-9_-]{32,}",
    "a Tavily API key": r"tvly-[A-Za-z0-9_-]{20,}",
    "a Discord bot token": r"[MNO][A-Za-z0-9_-]{23,27}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}",
    "a GitHub token": r"gh[pousr]_[A-Za-z0-9]{36,}",
    "an AWS access key id": r"AKIA[0-9A-Z]{16}",
    "a private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "a value for one of this project's .env keys": r"\b(?:OPENAI_API_KEY|TAVILY_API_KEY|HEYGEN_API_KEY|DISCORD_BOT_TOKEN)\s*[=:]\s*[\"']?[^\s\"']{8,}",
}


def found_secrets(prompt: str) -> list[str]:
    return [kind for kind, pattern in SECRET_PATTERNS.items() if re.search(pattern, prompt)]


try:
    kinds = found_secrets(json.load(sys.stdin)["prompt"])
    reason = f"Prompt blocked: it looks like it contains {', '.join(kinds)}. Remove the secret and resend; if it was real, rotate it." if kinds else None
except Exception as exc:  # a broken guard must fail closed
    reason = f"Prompt blocked: the secret guard itself failed ({exc!r})."
if reason:
    print(json.dumps({"decision": "block", "reason": reason}))
