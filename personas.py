from pathlib import Path
from dotenv import load_dotenv
from state import Persona

load_dotenv()

SELECTED_MODEL = "gpt-6-luna"

# gpt-6-luna's Chat Completions endpoint rejects function tools while reasoning is on, so the three agents that call tools turn it off. Lead calls no tools and keeps reasoning, which its routing decisions benefit from.
NO_REASONING = {"reasoning_effort": "none"}

# Each "skills" list names folders in .claude/skills/ that persona may load on demand. Lead's stays empty: its routing call has no tool loop, so it can't call load_skill.
PERSONAS: dict[Persona, dict] = {
    "lead": {
        "model": SELECTED_MODEL,
        "skills": [],
        "role": "Team lead: owns the job from request to finished deliverables, routes work to the right specialist, picks the draft, keeps the brief, and asks the user only when blocked.",
        "username": "Liam",
        "avatar_url": "https://cdn.discordapp.com/attachments/1553326533769302098/1553346556025901187/liam.jpg?ex=6ab8ea36&is=6ab798b6&hm=6998f8a6d251110f2bee4c74bbf3197f22b95affa929a6d9ef6b968264c0bf8b&",
    },
    "scout": {
        "model": SELECTED_MODEL,
        **NO_REASONING,
        "skills": ["source-vetting", "untrusted-input", "fact-grounding"],
        "role": "Researcher: finds current, sourced facts, trends and audience angles on the web.",
        "username": "Stark",
        "avatar_url": "https://cdn.discordapp.com/attachments/1553326533769302098/1553346557661810698/stark.jpg?ex=6ab8ea37&is=6ab798b7&hm=0b10f3a5ef6bbc67110e8c0d4d56138b9104bc018b44aee650db968fd1cbd08d&",
    },
    "content": {
        "model": SELECTED_MODEL,
        **NO_REASONING,
        "temperature": 0.7,
        "skills": ["caption-writing", "platform-specs", "fact-grounding"],
        "role": "Copywriter: writes, revises and locks in the post copy.",
        "username": "Claire",
        "avatar_url": "https://cdn.discordapp.com/attachments/1553326533769302098/1553346555371720774/claire.jpg?ex=6ab8ea36&is=6ab798b6&hm=fba20c1df1bec8cde8a7ed1e8da2666028fe4f5200777882cce553d004e37892&",
    },
    "producer": {
        "model": SELECTED_MODEL,
        **NO_REASONING,
        "skills": ["spoken-script", "fact-grounding"],
        "role": "Video producer: turns the chosen copy into a spoken script and renders the avatar video.",
        "username": "Paul",
        "avatar_url": "https://cdn.discordapp.com/attachments/1553326533769302098/1553346556718088222/paul.jpg?ex=6ab8ea36&is=6ab798b6&hm=ec846bc3ba380f703f1c61d43a3471a617bb110109aedf27fd208447a1314061&",
    },
}

_NON_LLM_KEYS = {"skills", "role", "username", "avatar_url"}


def llm_kwargs(persona: Persona) -> dict:
    """Just the ChatOpenAI-constructor-relevant subset of a persona's config, excluding the role description and Discord display keys."""
    return {k: v for k, v in PERSONAS[persona].items() if k not in _NON_LLM_KEYS}


PERSONAS_DIR = Path(__file__).parent / "personas"


def load_persona(persona: Persona) -> str:
    """Reads personas/<persona>.md fresh on every call (no caching), so editing a persona file takes effect on the next message without restarting the bot."""
    return (PERSONAS_DIR / f"{persona}.md").read_text().strip()


def load_team() -> str:
    """The shared team charter (personas/team.md), prepended to every persona's system prompt. Also read fresh on every call."""
    return (PERSONAS_DIR / "team.md").read_text().strip()


SKILLS_DIR = Path(__file__).parent / ".claude" / "skills"  # the same folders Claude Code reads, so every skill exists once


def skill_catalog(persona: Persona) -> str:
    """The index of skills this persona may load, one line each (name, description, when to use) taken from the SKILL.md frontmatter. Only this goes in the prompt; the full text is fetched on demand with load_skill. Empty when the persona has none."""
    names = PERSONAS[persona]["skills"]
    if not names:
        return ""
    lines = []
    for name in names:
        frontmatter = (SKILLS_DIR / name / "SKILL.md").read_text().split("---")[1]
        fields = dict(line.split(": ", 1) for line in frontmatter.strip().splitlines())
        lines.append(f"- {name}: {fields['description']}. {fields['when_to_use']}")
    intro = "## Skills\nBefore you start, load any skill whose description fits your task with `load_skill(name)`. A skill may point you to an extra file such as reference.md: load it with `load_skill(name, file)`."
    return intro + "\n" + "\n".join(lines)


def read_skill(name: str, file: str = "SKILL.md") -> str:
    """The text of one file in a skill folder without its frontmatter, with ${CLAUDE_SKILL_DIR} replaced by the folder's path. Refuses any `file` outside that folder, since the model chooses it."""
    folder = (SKILLS_DIR / name).resolve()
    path = (folder / file).resolve()
    if path.parent != folder:
        raise ValueError(f"{file!r} is not a file in the {name} skill")
    text = path.read_text()
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return text.strip().replace("${CLAUDE_SKILL_DIR}", str(folder))