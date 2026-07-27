"""Turning the supplied workbook into an analysable warehouse.

The pipeline is three steps, each independently testable:

``excel_loader``  read and validate the two worksheets
``normalize``     clean names, derive molecule tokens and treatment archetypes
``spaces``        roll SKUs up into the candidate opportunity spaces

``build_warehouse`` runs all three and persists the result to DuckDB.
"""

from .build_warehouse import build_warehouse
from .excel_loader import load_cardiac_workbook, load_glossary
from .normalize import normalize_cardiac_frame
from .spaces import SPACE_LEVELS, build_all_spaces

__all__ = [
    "SPACE_LEVELS",
    "build_all_spaces",
    "build_warehouse",
    "load_cardiac_workbook",
    "load_glossary",
    "normalize_cardiac_frame",
]
