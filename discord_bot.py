"""Discord layer.

The bot's own login is only used to listen for messages. Every agent reply is posted through a per-channel webhook with username/avatar_url overridden to match whichever persona is speaking, so the channel looks like a team of separate people rather than one bot.

Each Discord channel is one persistent LangGraph thread (thread_id = channel.id). Every user message becomes one graph turn: lead routes, specialists work, and each agent's message is posted the moment its node finishes rather than after the whole turn. Turns in the same channel run one at a time.

Command:
cd /Users/mac/Documents/Important/Self-study/agentic/diverse_marketing_agents
/opt/miniconda3/envs/langchain/bin/python discord_bot.py
"""
import asyncio
import os
from pathlib import Path

import discord
from dotenv import load_dotenv
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from graph import build_graph
from personas import PERSONAS
from tools import set_render_handler, thread_lock

load_dotenv()

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]

DB_PATH = Path(__file__).parent / "checkpoints.sqlite"
WEBHOOK_NAME = "AI Company Webhook"
MESSAGE_CHUNK = 1900  # Discord rejects messages over 2000 characters
TURN_TIMEOUT_SECONDS = 15 * 60  # a hung call would never raise, and would hold its channel's lock forever
RECURSION_LIMIT = 15  # LangGraph's default is ~10000; a normal turn is at most about 9 steps (the longest is a full run: research, drafts, pick, script), so this only trips on a runaway lead/specialist loop

# Cache of channel.id -> webhook handle only. Safe to lose on restart: Discord is the source of truth for the webhook's existence, so a cache miss just costs one lookup via channel.webhooks().
webhooks: dict[int, discord.Webhook] = {}

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

app = None  # built in main(), once the checkpointer's connection is open


async def get_webhook(channel: discord.TextChannel) -> discord.Webhook:
    if channel.id in webhooks:
        return webhooks[channel.id]

    existing = await channel.webhooks()
    hook = next((w for w in existing if w.name == WEBHOOK_NAME), None)
    if hook is None:
        hook = await channel.create_webhook(name=WEBHOOK_NAME)

    webhooks[channel.id] = hook
    return hook


def chunk_text(text: str, limit: int = MESSAGE_CHUNK) -> list[str]:
    """Splits on a paragraph, line or word boundary (in that order of preference) so each piece fits Discord's message limit."""
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


async def post_as(hook: discord.Webhook, speaker: str, content: str) -> None:
    persona = PERSONAS[speaker]
    for part in chunk_text(content):
        # allowed_mentions=none: agent text can quote web pages, and a stray @everyone must never ping the server.
        await hook.send(
            content=part,
            username=persona["username"],
            avatar_url=persona["avatar_url"],
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def handle_turn(channel: discord.TextChannel, user_line: str) -> None:
    """Runs one graph turn for this channel and posts each agent's message as its node finishes."""
    thread_id = str(channel.id)
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}
    turn_input = {"messages": [{"speaker": "user", "content": user_line}]}
    hook = await get_webhook(channel)
    async with thread_lock(thread_id), channel.typing(), asyncio.timeout(TURN_TIMEOUT_SECONDS):
        async for update in app.astream(turn_input, config, stream_mode="updates"):
            for node_output in update.values():
                for msg in node_output.get("messages", []):
                    await post_as(hook, msg["speaker"], msg["content"])


def reply_prefix(message: discord.Message) -> str:
    """If the user replied to one of the team's messages, tells the agents which one, since that is how the user addresses a specific teammate."""
    target = message.reference.resolved if message.reference else None
    if not isinstance(target, discord.Message):
        return ""
    snippet = target.content.strip().replace("\n", " ")[:300]
    return f'(replying to {target.author.display_name}: "{snippet}") '


async def on_render_finished(thread_id: str, result: dict) -> None:
    """Called by tools.py when a background HeyGen render ends: records it on the thread and tells the channel."""
    if result["status"] == "completed":
        text = f"The video is ready: {result['video_url']}"
    elif result["status"] == "failed":
        text = f"The render failed ({result['error']}). Tell me if you'd like me to try again."
    else:
        text = "The render is taking far longer than usual, so I've stopped waiting on it. Ask me to check its status whenever you like."

    update = {"video_status": result["status"], "next_agent": "finish", "messages": [{"speaker": "producer", "content": text}]}
    if result["status"] == "completed":
        update["video_url"] = result["video_url"]

    # Held under the same lock as a graph turn so the two never write this thread's state concurrently. as_node="lead" plus next_agent="finish" leaves the thread with no pending step.
    async with thread_lock(thread_id):
        await app.aupdate_state({"configurable": {"thread_id": thread_id}}, update, as_node="lead")
    await post_as(await get_webhook(client.get_channel(int(thread_id))), "producer", text)


# discord.py announces each thing that happens over the connection as a named event: on_ready when login finishes, on_message for each new message

@client.event
async def on_ready():
    print(f"Logged in as {client.user} — listening only, posts go through webhooks.")


@client.event
async def on_message(message: discord.Message):
    if message.author.bot or message.webhook_id is not None:
        return
    if not isinstance(message.channel, discord.TextChannel):
        return
    text = message.clean_content.strip()
    if not text:
        return

    await handle_turn(message.channel, f"{message.author.display_name}: {reply_prefix(message)}{text}")


async def main() -> None:
    global app
    discord.utils.setup_logging()  # client.run() does this for you; client.start() doesn't
    async with AsyncSqliteSaver.from_conn_string(str(DB_PATH)) as checkpointer:
        app = build_graph(checkpointer)
        set_render_handler(on_render_finished)
        async with client:
            await client.start(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())