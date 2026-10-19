"""Offline test of the SDK bot's own logic (claude_bot.py, claude_tools.py): everything that does not depend on what the model decides. The guards and the permission callback, the in-process HeyGen tools and render watcher, persona routing from parent_tool_use_id, session resume and the per-channel lock. Claude Code and the real model are never started: `claude_bot.query` is swapped for a scripted stream of SDK messages, and Discord and HeyGen are faked.

What it cannot show is how the model uses any of this. That needs a live run through a real Discord channel, which costs money and is not repeatable.

Command:
cd /Users/mac/Documents/Important/Self-study/agentic/diverse_marketing_agents
/opt/miniconda3/envs/langchain/bin/python scripts/claude_bot_test.py
"""
import asyncio
import json
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from unittest import mock

# Set before any project import: claude_bot.py reads the token at import and heygen.py reads the avatar and voice ids when it fingerprints a script.
os.environ["DISCORD_BOT_TOKEN"] = "test"
os.environ["HEYGEN_AVATAR_ID"] = "avatar-test"
os.environ["HEYGEN_VOICE_ID"] = "voice-test"

import dotenv

dotenv.load_dotenv = lambda *args, **kwargs: False  # the test must never read the real .env
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claude_agent_sdk import AssistantMessage, PermissionResultAllow, PermissionResultDeny, ResultMessage, SystemMessage, TextBlock, ToolUseBlock

import claude_bot
import claude_tools
import approval  # .claude/hooks/approval.py; importable only after claude_tools has put that folder on sys.path

RENDER = "mcp__heygen__start_video_render"


class FakeHook:
    def __init__(self):
        self.posts: list[tuple[str, str]] = []

    async def send(self, content, username, avatar_url, allowed_mentions):
        self.posts.append((username, content))


class FakeChannel:
    id = 4242

    @asynccontextmanager
    async def typing(self):
        yield


def stream(session_id: str, *messages) -> list:
    """What one turn of Claude Code emits: the init frame, the content, then the result."""
    result = ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id=session_id, total_cost_usd=0.01)
    return [SystemMessage(subtype="init", data={"session_id": session_id}), *messages, result]


def said(text: str, parent: str | None = None, *blocks) -> AssistantMessage:
    return AssistantMessage(content=[TextBlock(text=text), *blocks], model="fake", parent_tool_use_id=parent)


async def test_guards(root: Path) -> None:
    workspace = claude_tools.WORKSPACE
    inside, outside = str(workspace / "job" / "chosen.md"), str(root / "claude_bot.py")

    assert claude_tools.file_problem("Write", {"file_path": inside, "content": "x"}) is None
    assert claude_tools.file_problem("Write", {"file_path": outside, "content": "x"}), "a write outside workspace/ was allowed"
    assert claude_tools.file_problem("Edit", {"file_path": str(workspace / ".." / "claude_bot.py")}), "a .. path got out of workspace/"
    assert claude_tools.file_problem("Read", {"file_path": str(claude_tools.ROOT / ".env")}), "a read of .env was allowed"
    assert claude_tools.file_problem("Read", {"file_path": str(claude_tools.ROOT / "personas" / "lead.md")}) is None
    assert claude_tools.file_problem("Read", {}), "a malformed call must fail closed"
    (workspace / "link").symlink_to(root)
    assert claude_tools.file_problem("Write", {"file_path": str(workspace / "link" / "evil.md"), "content": "x"}), "a symlink led out of workspace/"
    long_script = " ".join(["word"] * 60)
    assert claude_tools.file_problem("Write", {"file_path": str(workspace / "job" / "video_script.md"), "content": long_script}), "a script over the cap was saved"
    assert claude_tools.file_problem("Write", {"file_path": str(workspace / "job" / "drafts.md"), "content": long_script}) is None, "the word cap must only apply to the video script"

    # authorize: the list, the file rules and the approval gate in one place
    assert isinstance(await claude_tools.authorize("WebSearch", {}, None), PermissionResultAllow)
    for name in ("Bash", "NotebookEdit", "mcp__claude_ai_Notion__notion-create-pages"):
        assert isinstance(await claude_tools.authorize(name, {}, None), PermissionResultDeny), f"{name} was allowed"
    assert isinstance(await claude_tools.authorize("Write", {"file_path": outside, "content": "x"}, None), PermissionResultDeny)

    job = workspace / "demo"
    job.mkdir()
    script, approved = job / "video_script.md", job / "approved"
    script.write_text("Short script.\n")
    event = {"tool_input": {"job": "demo"}}
    assert isinstance(await claude_tools.authorize(RENDER, event["tool_input"], None), PermissionResultDeny), "authorize allowed a render with no approval"
    assert (await claude_tools.render_gate(event, None, {}))["hookSpecificOutput"]["permissionDecision"] == "deny", "the render hook let an unapproved render through"
    approved.write_text("approved\n")
    os.utime(script, (1_000, 1_000))
    os.utime(approved, (2_000, 2_000))
    assert isinstance(await claude_tools.authorize(RENDER, event["tool_input"], None), PermissionResultAllow), "authorize refused an approved render"
    assert await claude_tools.render_gate(event, None, {}) == {}, "the render hook refused an approved render"
    os.utime(script, (3_000, 3_000))  # the script was edited after the approval
    assert isinstance(await claude_tools.authorize(RENDER, event["tool_input"], None), PermissionResultDeny), "a script edited after the approval still rendered"
    assert isinstance(await claude_tools.authorize(RENDER, {"job": "../etc"}, None), PermissionResultDeny), "a job name that is a path was accepted"
    hook_event = {"tool_name": "Write", "tool_input": {"file_path": outside, "content": "x"}}
    assert (await claude_tools.file_guard(hook_event, None, {}))["hookSpecificOutput"]["permissionDecision"] == "deny"


async def test_heygen_tools() -> None:
    started: list[str] = []
    told: list[str] = []

    async def fake_start(script: str) -> str:
        started.append(script)
        return f"vid_{len(started)}"

    async def fake_status(video_id: str) -> dict:
        return {"status": "completed", "video_url": f"https://example.test/{video_id}.mp4"}

    async def notify(text: str) -> None:
        told.append(text)

    with mock.patch.multiple(claude_tools, heygen_start=fake_start, heygen_status=fake_status, RENDER_POLL_SECONDS=0):
        tools = {t.name: t.handler for t in claude_tools.heygen_tools(notify)}
        assert set(tools) == {"set_video_plan", "start_video_render", "check_video_status"}
        job = claude_tools.WORKSPACE / "tooljob"
        script = "We are hiring a barista. Come and say hello."

        too_long = await tools["set_video_plan"]({"job": "tooljob", "script": " ".join(["word"] * 60)})
        assert "Not saved" in too_long["content"][0]["text"] and not (job / "video_script.md").exists(), "an over-cap script was saved"
        await tools["set_video_plan"]({"job": "tooljob", "script": script})
        assert (job / "video_script.md").read_text().strip() == script

        try:
            await tools["start_video_render"]({"job": "tooljob"})
        except ValueError:
            pass
        else:
            raise AssertionError("the tool started a render with no approval, even without the hook")
        assert not started

        (job / "approved").write_text("approved\n")
        os.utime(job / "video_script.md", (1_000, 1_000))
        os.utime(job / "approved", (2_000, 2_000))
        await tools["start_video_render"]({"job": "tooljob"})
        await asyncio.gather(*claude_tools._background)
        assert started == [script], f"expected one render of the approved script, got {started}"
        assert told == ["Your video is ready: https://example.test/vid_1.mp4\nThe link expires, so download the file if you want to keep it."], f"unexpected notification: {told}"
        assert json.loads((job / "render.json").read_text())["status"] == "completed"

        again = await tools["start_video_render"]({"job": "tooljob"})
        assert "already" in again["content"][0]["text"] and len(started) == 1, "the same script rendered twice without replace_existing"
        await tools["start_video_render"]({"job": "tooljob", "replace_existing": True})
        await asyncio.gather(*claude_tools._background)
        assert len(started) == 2, "replace_existing did not start a new render"
        assert (await tools["check_video_status"]({"job": "tooljob"}))["content"][0]["text"] == "Completed: https://example.test/vid_2.mp4"
        assert (await tools["check_video_status"]({"job": "nojob"}))["content"][0]["text"] == "No render has been started yet."


async def test_turns(tmp: Path) -> None:
    hook, channel = FakeHook(), FakeChannel()
    claude_bot.webhooks[channel.id] = hook
    seen_options = []
    scripts: list = []
    running = {"now": 0, "max": 0}

    async def fake_query(*, prompt, options):
        seen_options.append(options)
        running["now"] += 1
        running["max"] = max(running["max"], running["now"])
        await asyncio.sleep(0.01)  # long enough that an unlocked second turn would overlap this one
        try:
            for message in scripts.pop(0):
                yield message
        finally:
            running["now"] -= 1

    with mock.patch.object(claude_bot, "query", fake_query), mock.patch.object(claude_bot, "SESSIONS_PATH", tmp / "sessions.json"), mock.patch.dict(claude_bot.sessions, clear=True), mock.patch.object(
        claude_bot, "get_session_info", lambda session_id, directory: object() if session_id == "s1" else None
    ):
        scripts.append(stream(
            "s1",
            said("On it.", None, ToolUseBlock(id="t1", name="Task", input={"subagent_type": "scout", "prompt": "research"})),
            said("Three facts.", "t1"),
            said("Picking draft 2.", None, ToolUseBlock(id="t2", name="Agent", input={"subagent_type": "marketing-team:content", "prompt": "choose"})),
            said("Locked in.", "t2"),
            said("Draft 2 it is.", None),
            said("A subagent nobody started.", "t-unknown"),
            said("   "),  # blank text is never posted
            said("x" * 4000, None),
        ))
        await claude_bot.handle_turn(channel, "Dana: make a post")
        expected = [("Liam", "On it."), ("Stark", "Three facts."), ("Liam", "Picking draft 2."), ("Claire", "Locked in."), ("Liam", "Draft 2 it is."), ("Liam", "A subagent nobody started.")]
        assert hook.posts[:6] == expected, f"posts were {hook.posts[:6]}"
        long_posts = [text for name, text in hook.posts[6:]]
        assert len(long_posts) >= 3 and all(len(t) <= claude_bot.MESSAGE_CHUNK for t in long_posts), "a long message was not split to fit Discord"
        assert seen_options[0].resume is None
        assert json.loads((tmp / "sessions.json").read_text()) == {"4242": "s1"}, "the session id was not saved"

        scripts.append(stream("s1", said("Back again.")))
        await claude_bot.handle_turn(channel, "Dana: and a video")
        assert seen_options[1].resume == "s1", "the next message did not resume the channel's session"

        claude_bot.sessions["4242"] = "vanished"
        scripts.append(stream("s2", said("Fresh start.")))
        await claude_bot.handle_turn(channel, "Dana: hello?")
        assert seen_options[2].resume is None, "a session file that no longer exists must not be resumed"
        assert claude_bot.sessions["4242"] == "s2"

        scripts.extend([stream("s2", said("first")), stream("s2", said("second"))])
        running["max"] = 0
        await asyncio.gather(claude_bot.handle_turn(channel, "Dana: one"), claude_bot.handle_turn(channel, "Dana: two"))
        assert running["max"] == 1, "two turns in one channel ran at the same time"

        failed = ResultMessage(subtype="error_max_budget_usd", duration_ms=1, duration_api_ms=1, is_error=True, num_turns=9, session_id="s2", errors=["budget"])
        scripts.append([failed])
        try:
            await claude_bot.handle_turn(channel, "Dana: expensive")
        except RuntimeError as exc:
            assert "error_max_budget_usd" in str(exc)
        else:
            raise AssertionError("a turn that hit its budget ended silently instead of raising")
        assert not channel_lock_held(), "a failed turn left the channel locked"


async def test_webhook_lookup() -> None:
    """A webhook of the same name made by another bot has no token, so the bot must create its own instead of failing on send."""
    class Hook:
        def __init__(self, token):
            self.name, self.token = claude_bot.WEBHOOK_NAME, token

    class Channel:
        id = 9001

        def __init__(self, existing):
            self.existing, self.created = existing, []

        async def webhooks(self):
            return self.existing

        async def create_webhook(self, name):
            self.created.append(name)
            return Hook("own-token")

    foreign, mine = Hook(None), Hook("my-token")
    with mock.patch.dict(claude_bot.webhooks, clear=True):
        channel = Channel([foreign])
        assert (await claude_bot.get_webhook(channel)).token == "own-token" and channel.created, "a token-less webhook from another bot was reused"
        claude_bot.webhooks.clear()
        channel = Channel([foreign, mine])
        assert await claude_bot.get_webhook(channel) is mine and not channel.created, "a usable webhook was not reused"


def channel_lock_held() -> bool:
    return claude_bot.channel_lock("4242").locked()


def test_options() -> None:
    async def notify(text: str) -> None:
        pass

    options = claude_bot.build_options("s1", notify)
    assert options.resume == "s1" and options.setting_sources == ["project"] and options.strict_mcp_config
    assert options.can_use_tool is claude_tools.authorize and options.hooks is claude_tools.HOOKS
    assert "Bash" not in options.tools and options.permission_mode is None, "the bot must have no shell and must not run in a bypass mode"
    assert options.max_turns and options.max_budget_usd, "a turn must be bounded in steps and in spend"
    assert options.env["HEYGEN_API_KEY"] == "" and options.env["DISCORD_BOT_TOKEN"] == "", "secrets the agents don't need were left in their environment"

    lead = options.agents["lead"]
    assert lead.initialPrompt is None, "the lead's initialPrompt would stop the first message of every session"
    assert "Agent(scout, content, producer)" in lead.tools, f"the lead's subagent list was split on its inner commas: {lead.tools}"
    assert lead.prompt.startswith("First read `personas/team.md`"), "the lead's prompt body was not taken from lead.md"
    assert "Bash" in lead.disallowedTools and lead.model and lead.skills


async def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        workspace = tmp / "workspace"
        workspace.mkdir()
        roots = {"WORKSPACE": workspace, "READ_ROOTS": [workspace, claude_tools.ROOT / "personas"], "WRITE_ROOTS": [workspace]}
        with mock.patch.multiple(claude_tools, **roots), mock.patch.object(approval, "WORKSPACE", workspace):
            await test_guards(tmp)
            await test_heygen_tools()
        await test_turns(tmp)
    await test_webhook_lookup()
    test_options()
    print("CLAUDE BOT TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())
