"""Cardiac Opportunity Agent.

An AI agent that reads the India Cardiac prescription-audit dataset, fuses it
with curated external signals, and ranks the opportunity spaces where Cipla has
a sustainable right to win over the next three to five years.

The package is layered so that the numbers and the words are produced by
different machinery:

``ingestion``  raw workbook to a typed DuckDB warehouse
``analytics``  deterministic scoring, forecasting and sensitivity analysis
``rag``        retrieval over a cited corpus of external signals
``agent``      the reasoning loop that plans, calls tools and narrates
``guardrails`` checks that stand between the model and the user
``api``/``ui`` delivery surfaces
"""

__version__ = "1.0.0"

__all__ = ["__version__"]
