"""Retrieval over the external-signal corpus.

The case requires the agent to combine the supplied dataset with "relevant
external signals". Those signals are curated markdown documents with structured
front matter, each carrying a source and a URL, so that anything the agent says
about the outside world can be traced to a citation in the appendix.

Two consumers:

* :mod:`~cardiac_agent.rag.retriever` answers free-text questions, returning
  passages with citation identifiers.
* :mod:`~cardiac_agent.rag.linker` maps signals onto opportunity spaces and
  produces the bounded ``trend_multiplier`` that feeds the future-potential
  pillar of the scorecard.
"""

from .corpus import Signal, SignalCorpus, load_corpus
from .linker import link_signals_to_spaces
from .retriever import RetrievedPassage, SignalRetriever

__all__ = [
    "RetrievedPassage",
    "Signal",
    "SignalCorpus",
    "SignalRetriever",
    "link_signals_to_spaces",
    "load_corpus",
]
