"""Prompt loading.

Prompts live as markdown files beside this module rather than as string
literals in code. Two reasons: a reviewer can read and edit the agent's
instructions without touching Python, and prompt changes show up as readable
diffs in version control, which is the only practical way to review them.

Loaded content is cached because the system prompt is re-sent on every turn of
the tool loop and is marked for prompt caching on the provider side; reading it
from disk each time would be pointless work.
"""

from __future__ import annotations

import functools
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent


@functools.lru_cache(maxsize=16)
def load_prompt(name: str) -> str:
    """Read a prompt by stem, e.g. ``load_prompt("system")``."""
    path = PROMPT_DIR / f"{name}.md"
    if not path.exists():
        available = sorted(candidate.stem for candidate in PROMPT_DIR.glob("*.md"))
        raise FileNotFoundError(f"No prompt named '{name}'. Available: {available}.")
    return path.read_text(encoding="utf-8").strip()


def clear_prompt_cache() -> None:
    """Drop cached prompts. Used by tests that write temporary prompt files."""
    load_prompt.cache_clear()


__all__ = ["PROMPT_DIR", "clear_prompt_cache", "load_prompt"]
