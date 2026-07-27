"""Load and parse the external-signal corpus.

Each signal is a markdown file with YAML front matter. The front matter is the
machine-readable part - what the signal applies to, which direction it pushes,
how strongly, and how much we trust it. The body is what the agent quotes.

Keeping the corpus as plain files in the repository rather than in a database
is a deliberate choice: a reviewer can read every claim the system makes about
the outside world, in a diff, without running anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..config import get_settings
from ..logging_config import get_logger

logger = get_logger(__name__)

_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)

#: How much a signal's stated magnitude is trusted.
CONFIDENCE_WEIGHTS: dict[str, float] = {"high": 1.0, "medium": 0.6, "low": 0.3}

#: Sign applied to the magnitude when computing a trend multiplier.
DIRECTION_SIGNS: dict[str, float] = {"tailwind": 1.0, "headwind": -1.0, "neutral": 0.0}


@dataclass
class Signal:
    """One external signal: its metadata, its text, and what it applies to."""

    id: str
    title: str
    category: str
    publisher: str
    source: str
    url: str
    published: str
    accessed: str
    confidence: str
    direction: str
    magnitude: float
    body: str
    path: Path
    molecules: list[str] = field(default_factory=list)
    segments: list[str] = field(default_factory=list)
    sub_segments: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    @property
    def signed_magnitude(self) -> float:
        """Magnitude with direction and confidence applied."""
        sign = DIRECTION_SIGNS.get(self.direction.lower(), 0.0)
        weight = CONFIDENCE_WEIGHTS.get(self.confidence.lower(), 0.5)
        return sign * self.magnitude * weight

    @property
    def is_internal(self) -> bool:
        """True when the signal is derived from the supplied data, not published."""
        return self.url.startswith("internal://")

    def citation(self) -> dict[str, str]:
        """Appendix-ready citation record."""
        return {
            "id": self.id,
            "title": self.title,
            "publisher": self.publisher,
            "source": self.source,
            "url": self.url,
            "published": str(self.published),
            "accessed": str(self.accessed),
            "confidence": self.confidence,
            "type": "Derived from supplied data" if self.is_internal else "External source",
        }

    def searchable_text(self) -> str:
        """Everything that should be matchable by the retriever."""
        applies = " ".join([*self.molecules, *self.segments, *self.sub_segments, *self.keywords])
        return f"{self.title}\n{self.category} {applies}\n{self.body}"


@dataclass
class SignalCorpus:
    """The full set of loaded signals, with lookup helpers."""

    signals: list[Signal]

    def __len__(self) -> int:
        return len(self.signals)

    def __iter__(self):
        return iter(self.signals)

    def by_id(self, signal_id: str) -> Signal | None:
        for signal in self.signals:
            if signal.id.lower() == signal_id.lower():
                return signal
        return None

    def citations(self) -> list[dict[str, str]]:
        """Every citation, ordered by identifier, for the appendix."""
        return [signal.citation() for signal in sorted(self.signals, key=lambda s: s.id)]

    def external_only(self) -> list[Signal]:
        return [signal for signal in self.signals if not signal.is_internal]


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _parse_signal(path: Path) -> Signal | None:
    """Parse one markdown signal file. Returns ``None`` if malformed."""
    text = path.read_text(encoding="utf-8")
    match = _FRONT_MATTER.match(text)
    if not match:
        logger.warning("signal.no_front_matter", path=str(path))
        return None

    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        logger.warning("signal.bad_yaml", path=str(path), error=str(exc))
        return None

    if not isinstance(meta, dict) or "id" not in meta:
        logger.warning("signal.missing_id", path=str(path))
        return None

    applies = meta.get("applies_to") or {}
    if not isinstance(applies, dict):
        applies = {}

    return Signal(
        id=str(meta["id"]).strip(),
        title=str(meta.get("title", path.stem)),
        category=str(meta.get("category", "general")),
        publisher=str(meta.get("publisher", "")),
        source=str(meta.get("source", "")),
        url=str(meta.get("url", "")),
        published=str(meta.get("published", "")),
        accessed=str(meta.get("accessed", "")),
        confidence=str(meta.get("confidence", "medium")),
        direction=str(meta.get("direction", "neutral")),
        magnitude=float(meta.get("magnitude", 0.0) or 0.0),
        body=match.group(2).strip(),
        path=path,
        molecules=[m.upper() for m in _as_list(applies.get("molecules"))],
        segments=_as_list(applies.get("segments")),
        sub_segments=_as_list(applies.get("sub_segments")),
        keywords=[k.lower() for k in _as_list(applies.get("keywords"))],
    )


def load_corpus(directory: Path | None = None) -> SignalCorpus:
    """Load every signal document from disk.

    Args:
        directory: Corpus location. Defaults to ``data/external/signals``.

    Returns:
        A :class:`SignalCorpus`. An empty corpus is a warning, not an error:
        the deterministic analysis is complete without it, and the trend
        multiplier simply stays neutral.
    """
    resolved = directory or get_settings().signals_dir
    if not resolved.exists():
        logger.warning("corpus.missing_directory", path=str(resolved))
        return SignalCorpus(signals=[])

    signals: list[Signal] = []
    seen_ids: set[str] = set()
    for path in sorted(resolved.glob("*.md")):
        signal = _parse_signal(path)
        if signal is None:
            continue
        if signal.id in seen_ids:
            logger.warning("corpus.duplicate_id", signal_id=signal.id, path=str(path))
            continue
        seen_ids.add(signal.id)
        signals.append(signal)

    logger.info(
        "corpus.loaded",
        count=len(signals),
        external=sum(1 for s in signals if not s.is_internal),
        directory=str(resolved),
    )
    return SignalCorpus(signals=signals)


__all__ = [
    "CONFIDENCE_WEIGHTS",
    "DIRECTION_SIGNS",
    "Signal",
    "SignalCorpus",
    "load_corpus",
]
