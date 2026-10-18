"""Where the plugin's hooks read the project and keep their own state; the plugin folder itself holds neither."""
import os
from pathlib import Path

WORKSPACE = Path(os.environ["CLAUDE_PROJECT_DIR"]) / "workspace"  # the user's project, not the plugin: jobs live next to their code


def state_dir() -> Path:
    """The folder for a hook's scratch state file (loop counts, idle counts)."""
    data = os.environ["CLAUDE_PLUGIN_DATA"]  # survives plugin updates, unlike the plugin folder; a KeyError beats silently writing somewhere else
    Path(data).mkdir(parents=True, exist_ok=True)
    return Path(data)
