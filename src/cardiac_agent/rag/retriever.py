"""Hybrid retrieval over the signal corpus.

Two retrievers are fused with reciprocal rank fusion:

**BM25** over word tokens. Precise on exact terminology - "ezetimibe",
"cilnidipine", "NLEM" - which is most of what gets asked here.

**Character-trigram cosine** over TF-IDF vectors. Catches what BM25 misses:
misspellings, British/American variants, and morphological forms
("hypertensive" against "hypertension"). In a domain this dense with
near-identical drug names, that matters more than it would in general text.

Why not a transformer embedding index. The corpus is a few dozen chunks of
carefully written, highly technical text. Dense retrieval earns its keep on
large, noisy corpora where vocabulary mismatch dominates; here it would add an
API dependency, a model download and a source of run-to-run variation for
little measurable gain. The interface below is written so a dense backend can
be added as a third ranker without touching callers - see
``SignalRetriever.register_dense_ranker`` - but the default path is fully
deterministic and runs offline. That is the right trade for a system that has
to work reliably in a live demonstration.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from ..config import get_framework
from ..logging_config import get_logger
from .corpus import Signal, SignalCorpus, load_corpus

logger = get_logger(__name__)

_TOKEN = re.compile(r"[a-z0-9]+")

#: Words too common in this corpus to discriminate between signals.
STOPWORDS: frozenset[str] = frozenset(
    [
        "a", "an", "and", "are", "as", "at", "be", "been", "but", "by",
        "for", "from", "has", "have", "in", "into", "is", "it", "its",
        "of", "on", "or", "that", "the", "their", "there", "these",
        "this", "to", "was", "were", "which", "will", "with",
        # Corpus-specific: every signal document carries a "Why this matters
        # for prioritisation" heading, so these carry no discriminating signal.
        "why", "matters",
    ]
)

BM25_K1 = 1.5
BM25_B = 0.75


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens with stopwords removed."""
    return [token for token in _TOKEN.findall(text.lower()) if token not in STOPWORDS]


def char_trigrams(text: str) -> list[str]:
    """Character trigrams over the normalised string."""
    cleaned = re.sub(r"\s+", " ", text.lower().strip())
    if len(cleaned) < 3:
        return [cleaned] if cleaned else []
    return [cleaned[i : i + 3] for i in range(len(cleaned) - 2)]


@dataclass
class Chunk:
    """A retrievable passage, always traceable back to its signal."""

    chunk_id: str
    signal_id: str
    title: str
    text: str
    url: str
    publisher: str


@dataclass
class RetrievedPassage:
    """A retrieval hit, ready to be cited."""

    signal_id: str
    title: str
    text: str
    url: str
    publisher: str
    score: float
    rank: int

    def to_dict(self) -> dict:
        return {
            "citation": f"[{self.signal_id}]",
            "signal_id": self.signal_id,
            "title": self.title,
            "publisher": self.publisher,
            "url": self.url,
            "excerpt": self.text,
            "score": round(self.score, 4),
            "rank": self.rank,
        }


class DenseRanker(Protocol):
    """Optional pluggable dense retriever."""

    def rank(self, query: str, chunks: list[Chunk], top_k: int) -> list[tuple[str, float]]:
        """Return ``(chunk_id, score)`` pairs ordered best first."""
        ...


def _chunk_signal(signal: Signal, target_words: int, overlap_words: int) -> list[Chunk]:
    """Split one signal into overlapping passages, respecting paragraphs.

    Splitting on blank lines rather than a fixed window keeps tables and
    bulleted definitions intact, which matters because several signals carry
    the metric definitions the agent has to quote verbatim.
    """
    paragraphs = [block.strip() for block in signal.body.split("\n\n") if block.strip()]
    if not paragraphs:
        return [
            Chunk(
                chunk_id=f"{signal.id}#0",
                signal_id=signal.id,
                title=signal.title,
                text=signal.title,
                url=signal.url,
                publisher=signal.publisher,
            )
        ]

    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_words = 0
    index = 0

    def flush() -> None:
        nonlocal buffer, buffer_words, index
        if not buffer:
            return
        text = "\n\n".join(buffer).strip()
        chunks.append(
            Chunk(
                chunk_id=f"{signal.id}#{index}",
                signal_id=signal.id,
                title=signal.title,
                # Prefixing the title makes every chunk self-describing, which
                # keeps a mid-document passage useful when quoted alone.
                text=f"{signal.title}\n\n{text}",
                url=signal.url,
                publisher=signal.publisher,
            )
        )
        index += 1
        if overlap_words > 0:
            tail = " ".join(text.split()[-overlap_words:])
            buffer = [tail] if tail else []
            buffer_words = len(tail.split())
        else:
            buffer = []
            buffer_words = 0

    for paragraph in paragraphs:
        words = len(paragraph.split())
        if buffer_words + words > target_words and buffer:
            flush()
        buffer.append(paragraph)
        buffer_words += words
    buffer_words = 0
    flush()
    return chunks


class SignalRetriever:
    """Hybrid lexical retriever over the external-signal corpus."""

    def __init__(
        self,
        corpus: SignalCorpus | None = None,
        *,
        chunk_words: int | None = None,
        overlap_words: int | None = None,
        rrf_k: int | None = None,
    ) -> None:
        framework = get_framework()
        # Config is expressed in tokens; words are close enough for chunking and
        # avoid pulling in a tokeniser dependency for a few dozen documents.
        self.chunk_words = int(
            chunk_words or framework.get_path("rag.chunk_tokens", 320) * 0.75
        )
        self.overlap_words = int(
            overlap_words or framework.get_path("rag.chunk_overlap_tokens", 60) * 0.75
        )
        self.rrf_k = int(rrf_k or framework.get_path("rag.rrf_k", 60))

        self.corpus = corpus if corpus is not None else load_corpus()
        self.chunks: list[Chunk] = [
            chunk
            for signal in self.corpus
            for chunk in _chunk_signal(signal, self.chunk_words, self.overlap_words)
        ]
        self._dense: DenseRanker | None = None
        self._build_index()

        logger.info(
            "retriever.ready",
            signals=len(self.corpus),
            chunks=len(self.chunks),
            vocabulary=len(self._document_frequency),
        )

    # -- Index construction -------------------------------------------------

    def _build_index(self) -> None:
        self._tokens: list[list[str]] = [tokenize(chunk.text) for chunk in self.chunks]
        self._lengths = [len(tokens) for tokens in self._tokens]
        self._avg_length = (sum(self._lengths) / len(self._lengths)) if self._lengths else 0.0
        self._term_counts: list[Counter] = [Counter(tokens) for tokens in self._tokens]

        self._document_frequency: Counter = Counter()
        for tokens in self._tokens:
            self._document_frequency.update(set(tokens))

        self._trigram_vectors: list[dict[str, float]] = []
        trigram_df: Counter = Counter()
        trigram_counts = [Counter(char_trigrams(chunk.text)) for chunk in self.chunks]
        for counts in trigram_counts:
            trigram_df.update(counts.keys())

        total = max(len(self.chunks), 1)
        self._trigram_idf = {
            gram: math.log(1.0 + total / (1.0 + freq)) for gram, freq in trigram_df.items()
        }
        for counts in trigram_counts:
            vector = {
                gram: (1.0 + math.log(count)) * self._trigram_idf.get(gram, 0.0)
                for gram, count in counts.items()
            }
            norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
            self._trigram_vectors.append({k: v / norm for k, v in vector.items()})

    def register_dense_ranker(self, ranker: DenseRanker) -> None:
        """Attach an optional embedding-based ranker as a third retriever."""
        self._dense = ranker
        logger.info("retriever.dense_registered", ranker=type(ranker).__name__)

    # -- Individual rankers -------------------------------------------------

    def _bm25(self, query: str, top_k: int) -> list[tuple[int, float]]:
        query_terms = tokenize(query)
        if not query_terms or not self.chunks:
            return []
        total = len(self.chunks)
        scores: list[float] = [0.0] * total
        for term in query_terms:
            freq = self._document_frequency.get(term, 0)
            if freq == 0:
                continue
            idf = math.log(1.0 + (total - freq + 0.5) / (freq + 0.5))
            for index, counts in enumerate(self._term_counts):
                term_freq = counts.get(term, 0)
                if term_freq == 0:
                    continue
                length_norm = 1.0 - BM25_B + BM25_B * (
                    self._lengths[index] / self._avg_length if self._avg_length else 1.0
                )
                scores[index] += idf * (term_freq * (BM25_K1 + 1.0)) / (
                    term_freq + BM25_K1 * length_norm
                )
        ranked = sorted(enumerate(scores), key=lambda pair: pair[1], reverse=True)
        return [pair for pair in ranked[:top_k] if pair[1] > 0.0]

    def _trigram(self, query: str, top_k: int) -> list[tuple[int, float]]:
        counts = Counter(char_trigrams(query))
        if not counts or not self.chunks:
            return []
        vector = {
            gram: (1.0 + math.log(count)) * self._trigram_idf.get(gram, 0.0)
            for gram, count in counts.items()
        }
        norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
        vector = {k: v / norm for k, v in vector.items()}

        scores: list[tuple[int, float]] = []
        for index, doc_vector in enumerate(self._trigram_vectors):
            # Iterate the shorter side; query vectors are far smaller.
            similarity = sum(weight * doc_vector.get(gram, 0.0) for gram, weight in vector.items())
            if similarity > 0.0:
                scores.append((index, similarity))
        scores.sort(key=lambda pair: pair[1], reverse=True)
        return scores[:top_k]

    # -- Fusion -------------------------------------------------------------

    def search(self, query: str, top_k: int | None = None) -> list[RetrievedPassage]:
        """Retrieve passages for a free-text query.

        Ranked lists from each retriever are combined with reciprocal rank
        fusion, which needs no score calibration between rankers - it only uses
        positions, so a BM25 score of 14.2 and a cosine of 0.31 can be merged
        without inventing a normalisation constant.
        """
        if not self.chunks:
            return []
        limit = int(top_k or get_framework().get_path("rag.top_k", 6))
        pool = max(limit * 4, 20)

        ranked_lists: list[list[int]] = [
            [index for index, _ in self._bm25(query, pool)],
            [index for index, _ in self._trigram(query, pool)],
        ]
        if self._dense is not None:
            positions = {chunk.chunk_id: index for index, chunk in enumerate(self.chunks)}
            dense_hits = self._dense.rank(query, self.chunks, pool)
            ranked_lists.append(
                [positions[chunk_id] for chunk_id, _ in dense_hits if chunk_id in positions]
            )

        fused: dict[int, float] = {}
        for ranking in ranked_lists:
            for position, index in enumerate(ranking, start=1):
                fused[index] = fused.get(index, 0.0) + 1.0 / (self.rrf_k + position)

        # One passage per signal: several chunks of the same document add
        # length, not evidence, and crowd out other sources.
        best_per_signal: dict[str, tuple[int, float]] = {}
        for index, score in fused.items():
            signal_id = self.chunks[index].signal_id
            if signal_id not in best_per_signal or score > best_per_signal[signal_id][1]:
                best_per_signal[signal_id] = (index, score)

        ordered = sorted(best_per_signal.values(), key=lambda pair: pair[1], reverse=True)[:limit]
        results = [
            RetrievedPassage(
                signal_id=self.chunks[index].signal_id,
                title=self.chunks[index].title,
                text=self.chunks[index].text,
                url=self.chunks[index].url,
                publisher=self.chunks[index].publisher,
                score=score,
                rank=rank,
            )
            for rank, (index, score) in enumerate(ordered, start=1)
        ]
        logger.info("retriever.search", query=query[:120], hits=len(results))
        return results

    def score_for_terms(self, terms: list[str]) -> dict[str, float]:
        """Relevance of every signal to a set of terms, used by the linker."""
        if not terms:
            return {}
        query = " ".join(terms)
        scores: dict[str, float] = {}
        for index, score in self._bm25(query, len(self.chunks)):
            signal_id = self.chunks[index].signal_id
            scores[signal_id] = max(scores.get(signal_id, 0.0), score)
        peak = max(scores.values(), default=0.0)
        if peak <= 0.0:
            return {}
        return {signal_id: score / peak for signal_id, score in scores.items()}


def build_retriever(corpus: SignalCorpus | None = None) -> SignalRetriever:
    """Convenience factory, mainly so callers do not import the class directly."""
    return SignalRetriever(corpus)


__all__ = [
    "Chunk",
    "DenseRanker",
    "RetrievedPassage",
    "SignalRetriever",
    "build_retriever",
    "char_trigrams",
    "tokenize",
]
