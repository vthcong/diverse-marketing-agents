"""Discord layer.

Routing:
  - channel.id is used directly as the graph's thread_id -> one persistent LangGraph thread per Discord channel.
  - If the thread is currently paused on an interrupt(), the message is treated as the user's answer and resumes the run via Command(resume=message.content).
  - Otherwise it's treated as a new content request and starts a fresh run on that thread.
"""
import asyncio
import os

import discord
from dotenv import load_dotenv
from langgraph.types import Command

from graph import build_graph

load_dotenv()

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]

WEBHOOK_NAME = "AI Company Webhook"

PERSONAS = {
    "lead": {
        "username": "Liam (Lead)",
        "avatar_url": "https://cdn.discordapp.com/attachments/1553326533769302098/1553346556025901187/liam.jpg?ex=6ab8ea36&is=6ab798b6&hm=6998f8a6d251110f2bee4c74bbf3197f22b95affa929a6d9ef6b968264c0bf8b&",
    },
    "scout": {
        "username": "Stark (Scout)",
        "avatar_url": "https://cdn.discordapp.com/attachments/1553326533769302098/1553346557661810698/stark.jpg?ex=6ab8ea37&is=6ab798b7&hm=0b10f3a5ef6bbc67110e8c0d4d56138b9104bc018b44aee650db968fd1cbd08d&",
    },
    "content": {
        "username": "Claire (Content)",
        "avatar_url": "https://cdn.discordapp.com/attachments/1553326533769302098/1553346555371720774/claire.jpg?ex=6ab8ea36&is=6ab798b6&hm=fba20c1df1bec8cde8a7ed1e8da2666028fe4f5200777882cce553d004e37892&",
    },
    "producer": {
        "username": "Paul (Producer)",
        "avatar_url": "https://cdn.discordapp.com/attachments/1553326533769302098/1553346556718088222/paul.jpg?ex=6ab8ea36&is=6ab798b6&hm=ec846bc3ba380f703f1c61d43a3471a617bb110109aedf27fd208447a1314061&",
    },
}

# Cache of channel.id -> webhook handle only. Safe to lose on restart -- Discord itself is the source of truth for the webhook's existence, so a cache miss just costs one extra lookup via channel.webhooks().
# For posted_count/awaiting_resume, they're derived fresh from app.aget_state() in on_message instead, since that checkpoint (not bot memory) is the actual source of truth for what's been posted and whether a thread is paused.
webhooks: dict[int, discord.Webhook] = {}

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

app = None  # built asynchronously in main() before the client connects -- AsyncSqliteSaver needs a running event loop to open its connection.


async def get_webhook(channel: discord.TextChannel) -> discord.Webhook:
    if channel.id in webhooks:
        return webhooks[channel.id]

    existing = await channel.webhooks()
    hook = next((w for w in existing if w.name == WEBHOOK_NAME), None)
    if hook is None:
        hook = await channel.create_webhook(name=WEBHOOK_NAME)

    webhooks[channel.id] = hook
    return hook


async def post_as(hook: discord.Webhook, speaker: str, content: str) -> None:
    persona = PERSONAS[speaker]
    await hook.send(content=content, username=persona["username"], avatar_url=persona["avatar_url"])


async def post_result(channel: discord.TextChannel, result: dict, already_posted: int) -> None:
    hook = await get_webhook(channel)

    new_messages = result.get("messages", [])[already_posted:]
    for msg in new_messages:
        await post_as(hook, msg["speaker"], msg["content"])

    if "__interrupt__" in result:
        prompt = result["__interrupt__"][0].value
        await post_as(hook, prompt["speaker"], prompt["content"])


@client.event
async def on_ready():
    print(f"Logged in as {client.user} — listening only, posts go through webhooks.")


@client.event
async def on_message(message: discord.Message):
    if message.author.bot or message.webhook_id is not None:
        return
    if not isinstance(message.channel, discord.TextChannel):
        return

    channel_id = message.channel.id
    config = {"configurable": {"thread_id": str(channel_id)}}

    # The checkpoint is the source of truth for both of these -- not bot memory -- so they're correct even on the first message after a restart, unlike a locally cached dict would be.
    snapshot = await app.aget_state(config)
    already_posted = len(snapshot.values.get("messages", []))
    resuming = bool(snapshot.next)

    if resuming:
        result = await app.ainvoke(Command(resume=message.content), config)
    else:
        initial_state = {
            "request": message.content,
            "scout_findings": None,
            "draft_options": None,
            "chosen_draft": None,
            "video_tier": None,
            "video_url": None,
            "stage": "new",
            "messages": [],
        }
        result = await app.ainvoke(initial_state, config)

    await post_result(message.channel, result, already_posted)


async def main() -> None:
    global app
    app = await build_graph()
    async with client:
        await client.start(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())