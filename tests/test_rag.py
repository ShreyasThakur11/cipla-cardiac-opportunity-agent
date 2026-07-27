"""Corpus, retrieval and signal-linking tests."""

from __future__ import annotations

import pandas as pd
import pytest

from cardiac_agent.rag.corpus import Signal, SignalCorpus, load_corpus
from cardiac_agent.rag.linker import link_signals_to_spaces
from cardiac_agent.rag.retriever import SignalRetriever, char_trigrams, tokenize


def _signal(**overrides) -> Signal:
    base = {
        "id": "S-TEST",
        "title": "Test signal",
        "category": "guidelines",
        "publisher": "Test publisher",
        "source": "Test source",
        "url": "https://example.org/test",
        "published": "2025",
        "accessed": "2026-07-26",
        "confidence": "high",
        "direction": "tailwind",
        "magnitude": 0.10,
        "body": "Ezetimibe is recommended as an add-on to a maximally tolerated statin.",
        "path": None,
        "molecules": ["EZETIMIBE"],
        "segments": [],
        "sub_segments": ["Statins Comb."],
        "keywords": ["ezetimibe", "ldl"],
    }
    base.update(overrides)
    return Signal(**base)


class TestSignalSemantics:
    def test_signed_magnitude_applies_direction(self):
        assert _signal(direction="tailwind").signed_magnitude > 0
        assert _signal(direction="headwind").signed_magnitude < 0
        assert _signal(direction="neutral").signed_magnitude == 0

    def test_confidence_discounts_magnitude(self):
        high = _signal(confidence="high").signed_magnitude
        medium = _signal(confidence="medium").signed_magnitude
        low = _signal(confidence="low").signed_magnitude
        assert high > medium > low > 0

    def test_internal_signals_are_marked(self):
        assert _signal(url="internal://dataset/cardiac").is_internal
        assert not _signal().is_internal

    def test_citation_is_appendix_ready(self):
        citation = _signal().citation()
        assert set(citation) >= {"id", "title", "publisher", "url", "accessed", "type"}


class TestCorpus:
    def test_ships_a_populated_corpus(self):
        corpus = load_corpus()
        assert len(corpus) >= 10, "The repository should ship a usable signal corpus."

    def test_every_signal_has_a_source(self):
        for signal in load_corpus():
            assert signal.url, f"{signal.id} has no URL"
            assert signal.publisher, f"{signal.id} has no publisher"

    def test_identifiers_are_unique(self):
        corpus = load_corpus()
        identifiers = [signal.id for signal in corpus]
        assert len(identifiers) == len(set(identifiers))

    def test_lookup_by_id_is_case_insensitive(self):
        corpus = load_corpus()
        first = corpus.signals[0]
        assert corpus.by_id(first.id.lower()) is first


class TestTokenisation:
    def test_removes_stopwords(self):
        assert "the" not in tokenize("The market is growing")

    def test_trigrams_cover_the_string(self):
        assert char_trigrams("statin")[0] == "sta"


class TestRetrieval:
    @pytest.fixture(scope="class")
    def retriever(self):
        return SignalRetriever(load_corpus())

    def test_finds_the_relevant_signal(self, retriever):
        hits = retriever.search("ezetimibe statin combination guidelines", top_k=3)
        assert hits
        assert any("S-03" in hit.signal_id or "S-10" in hit.signal_id for hit in hits)

    def test_returns_one_passage_per_signal(self, retriever):
        hits = retriever.search("price control regulation NLEM", top_k=5)
        assert len({hit.signal_id for hit in hits}) == len(hits)

    def test_hits_are_citable(self, retriever):
        hits = retriever.search("hypertension prevalence", top_k=2)
        assert hits
        payload = hits[0].to_dict()
        assert payload["citation"].startswith("[S-")
        assert payload["excerpt"]

    def test_trigram_ranker_survives_a_misspelling(self, retriever):
        """Lexical fusion is here precisely so a near-miss still retrieves."""
        assert retriever.search("ezetimib", top_k=3)

    def test_empty_corpus_returns_nothing(self):
        assert SignalRetriever(SignalCorpus(signals=[])).search("anything") == []


class TestLinking:
    def _spaces(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "level": "molecule_combination",
                    "space_id": "MOL_EZE",
                    "space_label": "Statins Comb. | ROSUVASTATIN + EZETIMIBE",
                    "segment": "Lipid Regulators",
                    "sub_segment": "Statins Comb.",
                },
                {
                    "level": "molecule_combination",
                    "space_id": "MOL_OTHER",
                    "space_label": "ACEi | RAMIPRIL",
                    "segment": "Anti Hypertensives",
                    "sub_segment": "ACEi",
                },
                {
                    "level": "molecule_combination",
                    "space_id": "MOL_THIRD",
                    "space_label": "Nitrates | GLYCERYL TRINITRATE",
                    "segment": "Anti Angina",
                    "sub_segment": "Nitrates",
                },
            ]
        )

    def test_neutral_when_the_corpus_is_empty(self):
        spaces, links = link_signals_to_spaces(self._spaces(), SignalCorpus(signals=[]))
        assert (spaces["trend_multiplier"] == 1.0).all()
        assert links == []

    def test_multiplier_stays_inside_the_configured_band(self, framework):
        lower = framework.get_path("rag.trend_multiplier_min")
        upper = framework.get_path("rag.trend_multiplier_max")
        spaces, _ = link_signals_to_spaces(self._spaces(), load_corpus())
        assert spaces["trend_multiplier"].between(lower, upper).all()

    def test_differential_evidence_moves_the_ranking(self):
        """A signal on one space must lift it relative to the others."""
        corpus = SignalCorpus(signals=[_signal()])
        spaces, links = link_signals_to_spaces(self._spaces(), corpus)
        by_id = dict(zip(spaces["space_id"], spaces["trend_multiplier"], strict=False))
        assert by_id["MOL_EZE"] > by_id["MOL_OTHER"]
        assert links

    def test_universal_evidence_moves_nothing(self):
        """Centring means a signal that applies everywhere cannot tilt the ranking."""
        universal = _signal(
            id="S-ALL",
            molecules=[],
            sub_segments=[],
            segments=["Lipid Regulators", "Anti Hypertensives", "Anti Angina"],
            keywords=[],
        )
        spaces, _ = link_signals_to_spaces(self._spaces(), SignalCorpus(signals=[universal]))
        assert spaces["trend_multiplier"].nunique() == 1
        assert spaces["trend_multiplier"].iloc[0] == pytest.approx(1.0)

    def test_records_why_each_signal_attached(self):
        spaces, links = link_signals_to_spaces(self._spaces(), SignalCorpus(signals=[_signal()]))
        assert links
        assert all(link.match_reason for link in links)
