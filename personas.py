from pathlib import Path
from dotenv import load_dotenv
from state import Persona

load_dotenv()

MODEL_GPT_5_NANO = "gpt-5-nano"
MODEL_GPT_6_LUNA = "gpt-6-luna"

PERSONAS: dict[Persona, dict] = {
    "lead": {
        "model": MODEL_GPT_6_LUNA,
        "role": "Team lead: reads every message, routes work to the right specialist, keeps the brief, and tells the user where things stand.",
        "username": "Liam (Lead)",
        "avatar_url": "https://cdn.discordapp.com/attachments/1553326533769302098/1553346556025901187/liam.jpg?ex=6ab8ea36&is=6ab798b6&hm=6998f8a6d251110f2bee4c74bbf3197f22b95affa929a6d9ef6b968264c0bf8b&",
    },
    "scout": {
        "model": MODEL_GPT_5_NANO,
        "role": "Researcher: finds current, sourced facts, trends and audience angles on the web.",
        "username": "Stark (Scout)",
        "avatar_url": "https://cdn.discordapp.com/attachments/1553326533769302098/1553346557661810698/stark.jpg?ex=6ab8ea37&is=6ab798b7&hm=0b10f3a5ef6bbc67110e8c0d4d56138b9104bc018b44aee650db968fd1cbd08d&",
    },
    "content": {
        "model": MODEL_GPT_5_NANO,
        "temperature": 0.7,
        "role": "Copywriter: writes, revises and locks in the post copy.",
        "username": "Claire (Content)",
        "avatar_url": "https://cdn.discordapp.com/attachments/1553326533769302098/1553346555371720774/claire.jpg?ex=6ab8ea36&is=6ab798b6&hm=fba20c1df1bec8cde8a7ed1e8da2666028fe4f5200777882cce553d004e37892&",
    },
    "producer": {
        "model": MODEL_GPT_5_NANO,
        "role": "Video producer: turns the chosen copy into a spoken script and renders the avatar video.",
        "username": "Paul (Producer)",
        "avatar_url": "https://cdn.discordapp.com/attachments/1553326533769302098/1553346556718088222/paul.jpg?ex=6ab8ea36&is=6ab798b6&hm=ec846bc3ba380f703f1c61d43a3471a617bb110109aedf27fd208447a1314061&",
    },
}

_NON_LLM_KEYS = {"role", "username", "avatar_url"}


def llm_kwargs(persona: Persona) -> dict:
    """Just the ChatOpenAI-constructor-relevant subset of a persona's config, excluding the role description and Discord display keys."""
    return {k: v for k, v in PERSONAS[persona].items() if k not in _NON_LLM_KEYS}


SKILLS_DIR = Path(__file__).parent / "skills"


def load_skill(persona: Persona) -> str:
    """Reads skills/<persona>.md fresh on every call (no caching), so editing a skill file takes effect on the next message without restarting the bot."""
    return (SKILLS_DIR / f"{persona}.md").read_text().strip()


def load_team() -> str:
    """The shared team charter (skills/team.md), prepended to every persona's system prompt. Also read fresh on every call."""
    return (SKILLS_DIR / "team.md").read_text().strip()