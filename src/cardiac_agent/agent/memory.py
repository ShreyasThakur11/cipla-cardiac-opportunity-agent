"""Conversation memory.

The agent is stateless per question by design: every run re-derives its evidence
from the warehouse, so an answer can never be contaminated by a stale figure
carried over from an earlier turn. That is the right default for an analyst
tool where correctness matters more than conversational fluency.

What is worth remembering is the thread of the discussion - which spaces have
already been examined, what was recommended, what the user pushed back on. This
module keeps that, bounded to a configured number of turns, and renders it as a
short preamble the next question can be read against.

Deliberately excluded from memory: numbers. Recalling "you said 759 crore
earlier" would let a figure survive past the guardrail that checked it. Every
number is re-fetched, every time.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..config import get_framework


@dataclass
class Turn:
    """One question and the shape of the answer it received."""

    question: str
    intent: str
    tools_used: list[str]
    spaces_discussed: list[str]
    asked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def summary(self) -> str:
        spaces = ", ".join(self.spaces_discussed[:4]) if self.spaces_discussed else "none"
        return f"asked about {self.intent.replace('_', ' ')}; spaces examined: {spaces}"


class ConversationMemory:
    """Bounded record of the discussion so far."""

    def __init__(self, max_turns: int | None = None) -> None:
        limit = int(max_turns or get_framework().get_path("agent.memory_turns", 12))
        self._turns: deque[Turn] = deque(maxlen=limit)

    def __len__(self) -> int:
        return len(self._turns)

    def record(self, question: str, intent: str, tools_used: list[str], evidence: dict[str, Any]) -> None:
        """Add a turn, extracting which spaces were examined."""
        spaces: list[str] = []
        for key, payload in evidence.items():
            if not isinstance(payload, dict):
                continue
            if key.startswith("space_deep_dive") and "space_label" in payload:
                spaces.append(str(payload["space_label"]))
            elif key.startswith("rank_opportunity_spaces"):
                spaces.extend(
                    str(row.get("space_label", ""))
                    for row in payload.get("spaces", [])[:3]
                )
        deduped = list(dict.fromkeys(space for space in spaces if space))
        self._turns.append(
            Turn(question=question, intent=intent, tools_used=tools_used, spaces_discussed=deduped)
        )

    def preamble(self) -> str:
        """Short context block to prepend to the next question."""
        if not self._turns:
            return ""
        lines = [
            f"{index}. \"{turn.question[:110]}\" - {turn.summary()}"
            for index, turn in enumerate(self._turns, start=1)
        ]
        return (
            "Earlier in this conversation:\n"
            + "\n".join(lines)
            + "\n\nTreat these as context only. Re-fetch every figure you intend to state.\n"
        )

    def spaces_seen(self) -> list[str]:
        """Every space examined so far, most recent first."""
        seen: list[str] = []
        for turn in reversed(self._turns):
            for space in turn.spaces_discussed:
                if space not in seen:
                    seen.append(space)
        return seen

    def clear(self) -> None:
        self._turns.clear()


__all__ = ["ConversationMemory", "Turn"]
