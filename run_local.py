"""Local smoke test — no Discord involved.

Runs the graph end to end, manually playing the role of the Discord user at both interrupt points, to prove pause/resume works before we wire up the bot. This is exactly what discord_bot.py will do automatically: check the result for "__interrupt__", and if present, resume with Command(resume=<the user's next message>) instead of starting a new run.

Note: state["messages"] accumulates over the WHOLE thread (it's kept in the checkpointer), so every invoke()/resume call returns the full history so far, not just what's new. `already_posted` tracks how many messages we've printed for this thread, mirroring what the Discord bot will need to do to avoid reposting old messages every turn.
"""
import asyncio

from langgraph.types import Command

from graph import build_graph


def print_new_messages(result: dict, already_posted: int) -> int:
    messages = result.get("messages", [])
    for msg in messages[already_posted:]:
        print(f"  [{msg['speaker']}] {msg['content']}")
    return len(messages)


async def main():
    app = await build_graph()
    config = {"configurable": {"thread_id": "demo-channel-1"}}
    posted = 0

    print("--- starting run ---")
    result = await app.ainvoke(
        {
            "request": "Generate a post on LinkedIn with caption and video to hire a Graduate AI Engineer.",
            "scout_findings": None,
            "draft_options": None,
            "chosen_draft": None,
            "video_tier": None,
            "video_url": None,
            "stage": "new",
            "messages": [],
        },
        config,
    )
    posted = print_new_messages(result, posted)

    assert "__interrupt__" in result, "expected to pause after content"
    prompt = result["__interrupt__"][0].value
    print(f"\n[PAUSED as {prompt['speaker']}] {prompt['content']}")

    print("\n--- simulating user reply: '2' ---")
    result = await app.ainvoke(Command(resume="2"), config)
    posted = print_new_messages(result, posted)

    assert "__interrupt__" in result, "expected to pause after producer"
    prompt = result["__interrupt__"][0].value
    print(f"\n[PAUSED as {prompt['speaker']}] {prompt['content']}")

    print("\n--- simulating user reply: 'approve' ---")
    result = await app.ainvoke(Command(resume="approve"), config)
    posted = print_new_messages(result, posted)

    print("\n--- final state ---")
    print("stage:", result["stage"])
    print("chosen_draft:", result["chosen_draft"])
    print("video_url:", result["video_url"])


if __name__ == "__main__":
    asyncio.run(main())
