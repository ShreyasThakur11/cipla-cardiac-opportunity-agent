"""The analysis context: one object that holds a fully scored market.

Building the scorecard means reading the warehouse, deriving growth metrics,
computing competitive structure, evaluating right to win, linking external
signals and finally scoring. That chain is deterministic and takes a couple of
seconds, so it is done once per process and cached here rather than repeated on
every tool call.

Everything the agent can see comes from this object. If a number is not on an
:class:`AnalysisContext`, the agent has no way to produce it - which is the
property that makes the numeric guardrail enforceable.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from .analytics.competition import add_competition_metrics
from .analytics.metrics import add_growth_metrics, market_totals
from .analytics.rightowin import add_right_to_win_metrics
from .analytics.scoring import ScoreResult, build_scorecard
from .config import FrameworkConfig, get_framework, get_settings
from .logging_config import get_logger
from .rag.corpus import SignalCorpus, load_corpus
from .rag.linker import SpaceSignalLink, link_signals_to_spaces
from .rag.retriever import SignalRetriever

logger = get_logger(__name__)

WAREHOUSE_TABLES = (
    "sku_facts",
    "space_facts",
    "space_membership",
    "company_facts",
    "brand_facts",
    "glossary",
    "build_metadata",
)


class WarehouseMissingError(RuntimeError):
    """The DuckDB warehouse has not been built yet."""


@dataclass
class AnalysisContext:
    """A fully derived, scored view of the Cardiac market."""

    sku_facts: pd.DataFrame
    space_facts: pd.DataFrame
    membership: pd.DataFrame
    company_facts: pd.DataFrame
    brand_facts: pd.DataFrame
    glossary: pd.DataFrame
    metadata: dict[str, Any]
    enriched: pd.DataFrame
    score: ScoreResult
    corpus: SignalCorpus
    retriever: SignalRetriever
    signal_links: list[SpaceSignalLink]
    totals: dict[str, float]
    framework: FrameworkConfig
    warehouse_path: Path
    notes: list[str] = field(default_factory=list)

    # -- Lookups ------------------------------------------------------------

    @property
    def scored(self) -> pd.DataFrame:
        """Every space that survived the filters, with scores attached."""
        return self.score.scored

    @property
    def focal_label(self) -> str:
        return str(self.framework.get_path("market.focal_company_label", "Cipla"))

    @property
    def currency_unit(self) -> str:
        return str(self.framework.get_path("market.currency_unit", "INR crore"))

    @property
    def as_of(self) -> str:
        return str(self.framework.get_path("market.as_of", ""))

    def find_space(self, identifier: str, level: str | None = None) -> pd.Series | None:
        """Resolve a space by identifier or by a fragment of its label.

        The agent refers to spaces the way a human would - "the ezetimibe
        combination space" - so exact-identifier lookup alone would be too
        brittle to be useful.
        """
        frame = self.scored
        if level:
            frame = frame[frame["level"] == level]
        if frame.empty:
            return None

        needle = identifier.strip()
        exact = frame[frame["space_id"].str.lower() == needle.lower()]
        if not exact.empty:
            return exact.iloc[0]

        label_exact = frame[frame["space_label"].str.lower() == needle.lower()]
        if not label_exact.empty:
            return label_exact.iloc[0]

        contains = frame[frame["space_label"].str.contains(needle, case=False, regex=False)]
        if not contains.empty:
            # Prefer the largest match: a fragment such as "telmisartan" hits
            # many rows and the biggest is almost always what was meant.
            return contains.sort_values("value_t2", ascending=False).iloc[0]
        return None

    def space_signals(self, space_id: str) -> list[dict[str, Any]]:
        """Signals attached to one space, with their contributions."""
        return [
            {
                "signal_id": link.signal_id,
                "match_reason": link.match_reason,
                "contribution": link.contribution,
            }
            for link in self.signal_links
            if link.space_id == space_id
        ]

    def citations(self) -> list[dict[str, str]]:
        """Every source in the corpus, for the appendix."""
        return self.corpus.citations()


def _read_warehouse(path: Path) -> dict[str, pd.DataFrame]:
    if not path.exists():
        raise WarehouseMissingError(
            f"No warehouse at {path}. Run `cardiac-agent build` (or "
            "`python -m cardiac_agent.cli build`) after placing the Cardiac "
            "workbook in data/raw/."
        )
    connection = duckdb.connect(str(path), read_only=True)
    try:
        present = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
        missing = [table for table in WAREHOUSE_TABLES if table not in present]
        if missing:
            raise WarehouseMissingError(
                f"Warehouse at {path} is incomplete (missing {', '.join(missing)}). "
                "Rebuild it with `cardiac-agent build --force`."
            )
        return {
            table: connection.execute(f"SELECT * FROM {table}").fetch_df()
            for table in WAREHOUSE_TABLES
        }
    finally:
        connection.close()


def build_context(warehouse: Path | None = None) -> AnalysisContext:
    """Read the warehouse and derive the complete scored view.

    Args:
        warehouse: DuckDB file. Defaults to the configured location.

    Raises:
        WarehouseMissingError: The warehouse has not been built.
    """
    import json

    settings = get_settings()
    framework = get_framework()
    path = warehouse or settings.warehouse_path

    tables = _read_warehouse(path)
    metadata_frame = tables["build_metadata"]
    metadata = {str(row["key"]): json.loads(row["value"]) for _, row in metadata_frame.iterrows()}

    sku_facts = tables["sku_facts"]
    space_facts = tables["space_facts"]
    membership = tables["space_membership"]
    company_facts = tables["company_facts"]

    periods = framework.require("market.periods")
    latest_value_column = periods["value"]["t2"]

    notes: list[str] = []

    enriched = add_growth_metrics(space_facts)
    enriched = add_competition_metrics(enriched, company_facts)
    enriched = add_right_to_win_metrics(
        enriched, sku_facts, membership, value_column=latest_value_column
    )

    corpus = load_corpus()
    if len(corpus) == 0:
        notes.append(
            "External-signal corpus is empty; every trend multiplier is neutral "
            "and the analysis rests on the supplied dataset alone."
        )
    enriched, links = link_signals_to_spaces(
        enriched, corpus, sku_facts=sku_facts, membership=membership
    )

    score = build_scorecard(enriched, framework=framework)
    notes.extend(score.notes)

    totals = market_totals(enriched)
    retriever = SignalRetriever(corpus)

    logger.info(
        "context.ready",
        spaces_scored=len(score.scored),
        signals=len(corpus),
        market_value=round(totals["market_value_t2"], 1),
    )

    return AnalysisContext(
        sku_facts=sku_facts,
        space_facts=space_facts,
        membership=membership,
        company_facts=company_facts,
        brand_facts=tables["brand_facts"],
        glossary=tables["glossary"],
        metadata=metadata,
        enriched=enriched,
        score=score,
        corpus=corpus,
        retriever=retriever,
        signal_links=links,
        totals=totals,
        framework=framework,
        warehouse_path=path,
        notes=notes,
    )


@functools.lru_cache(maxsize=1)
def _cached_context(path_str: str) -> AnalysisContext:
    return build_context(Path(path_str))


def get_context(warehouse: Path | None = None, *, refresh: bool = False) -> AnalysisContext:
    """Process-wide cached analysis context.

    Args:
        warehouse: Override the warehouse location.
        refresh: Rebuild even if a cached context exists.
    """
    path = warehouse or get_settings().warehouse_path
    if refresh:
        _cached_context.cache_clear()
    return _cached_context(str(path))


def reset_context_cache() -> None:
    """Drop the cached context. Used after a rebuild and by tests."""
    _cached_context.cache_clear()


__all__ = [
    "AnalysisContext",
    "WarehouseMissingError",
    "build_context",
    "get_context",
    "reset_context_cache",
]
