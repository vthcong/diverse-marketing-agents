"""MCP server that lets the Claude Code agents speak in Discord under their own name and avatar.

The Discord channel plugin (discord@claude-plugins-official) delivers the user's messages into the session, but its reply tool always posts as the plugin's one bot. This server is the outbound half: post_as sends through the same per-channel webhook that discord_bot.py uses, with the username and avatar_url of the persona in personas.py, so the team looks like four people again. It only posts to channels the plugin itself allows (its access.json), because the chat_id comes from a model that may have read hostile text.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # a script run by path only has its own folder on sys.path, so the project root must be added to import personas.py

import httpx
from mcp.server.fastmcp import FastMCP

from personas import PERSONAS  # also runs load_dotenv(), which is where DISCORD_BOT_TOKEN comes from

API = "https://discord.com/api/v10"
WEBHOOK_NAME = "AI Company Webhook"  # the same name discord_bot.py uses, so a channel never ends up with two webhooks
MESSAGE_CHUNK = 1900  # Discord rejects messages over 2000 characters
STATE_DIR = Path(os.environ.get("DISCORD_STATE_DIR") or Path.home() / ".claude" / "channels" / "discord")  # where the plugin keeps access.json

mcp = FastMCP("discord_persona")

# Cache of chat_id -> (webhook id, webhook token) only. Safe to lose on restart: Discord is the source of truth, so a cache miss just costs one lookup.
webhooks: dict[str, tuple[str, str]] = {}


def chunk_text(text: str, limit: int = MESSAGE_CHUNK) -> list[str]:
    """Same splitter as discord_bot.chunk_text, copied because importing discord_bot would pull in the whole LangGraph app and its API keys."""
    text = text.strip()
    chunks = []
    while len(text) > limit:
        cut = limit
        for sep in ("\n\n", "\n", " "):
            i = text.rfind(sep, limit // 2, limit)
            if i != -1:
                cut = i
                break
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks


def _check_allowed(chat_id: str) -> None:
    groups = json.loads((STATE_DIR / "access.json").read_text())["groups"]
    if chat_id not in groups:  # checked before chat_id goes into any URL, and the keys are channel ids from /discord:access
        raise ValueError(f"Channel {chat_id} is not allowed for the Discord plugin. The user adds it with /discord:access in the terminal.")


async def _get_webhook(http: httpx.AsyncClient, chat_id: str) -> tuple[str, str]:
    if chat_id not in webhooks:
        headers = {"Authorization": f"Bot {os.environ['DISCORD_BOT_TOKEN']}"}
        listed = await http.get(f"{API}/channels/{chat_id}/webhooks", headers=headers)
        listed.raise_for_status()
        hook = next((w for w in listed.json() if w["name"] == WEBHOOK_NAME), None)
        if hook is None:
            created = await http.post(f"{API}/channels/{chat_id}/webhooks", headers=headers, json={"name": WEBHOOK_NAME})
            created.raise_for_status()
            hook = created.json()
        webhooks[chat_id] = (hook["id"], hook["token"])
    return webhooks[chat_id]


@mcp.tool()
async def post_as(persona: str, chat_id: str, text: str) -> str:
    """Post a message to a Discord channel as one member of the team. persona is lead, scout, content or producer, and the message appears under that teammate's own name and avatar. Pass chat_id from the inbound <channel> message. Post only as yourself."""
    if persona not in PERSONAS:
        raise ValueError(f"Unknown persona {persona!r}: use one of {', '.join(PERSONAS)}.")
    _check_allowed(chat_id)
    async with httpx.AsyncClient() as http:
        hook_id, hook_token = await _get_webhook(http, chat_id)
        for part in chunk_text(text):
            sent = await http.post(
                f"{API}/webhooks/{hook_id}/{hook_token}",
                json={
                    "content": part,
                    "username": PERSONAS[persona]["username"],
                    "avatar_url": PERSONAS[persona]["avatar_url"],
                    "allowed_mentions": {"parse": []},  # agent text can quote web pages, and a stray @everyone must never ping the server
                },
            )
            sent.raise_for_status()
    return f"Posted as {PERSONAS[persona]['username']}."


if __name__ == "__main__":
    mcp.run()
