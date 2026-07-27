"""Configuration loading.

Two sources feed the runtime:

* ``config/settings.yaml`` holds the analytical parameters - weights,
  thresholds, forecast assumptions. These are the numbers a reviewer may want
  to challenge, so they live in a file a non-programmer can edit.
* Environment variables (optionally via ``.env``) hold deployment concerns -
  credentials, paths, ports. These change per machine, not per analysis.

Keeping the two apart means the analysis is reproducible from the repository
alone, while secrets never enter version control.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# --------------------------------------------------------------------------
# Filesystem layout
# --------------------------------------------------------------------------

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parents[1]

DEFAULT_CONFIG_FILE = PROJECT_ROOT / "config" / "settings.yaml"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_RAW_DIR = DEFAULT_DATA_DIR / "raw"
DEFAULT_PROCESSED_DIR = DEFAULT_DATA_DIR / "processed"
DEFAULT_SIGNALS_DIR = DEFAULT_DATA_DIR / "external" / "signals"
DEFAULT_VECTORSTORE_DIR = DEFAULT_DATA_DIR / "vectorstore"

#: Filenames the loader will accept for the Cardiac workbook, tried in order.
CANDIDATE_WORKBOOK_NAMES = (
    "cardiac_dataset.xlsx",
    "Data Set_Ascend Season 4_2026.xlsx",
    "dataset.xlsx",
)

Provider = Literal["anthropic", "openai", "gemini", "none"]


class Settings(BaseSettings):
    """Deployment settings, read from the environment and ``.env``."""

    model_config = SettingsConfigDict(
        env_prefix="CARDIAC_",
        env_file=(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM ---------------------------------------------------------------
    llm_provider: Provider = "anthropic"
    llm_model: str = "claude-opus-5"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    llm_max_tokens: int = Field(default=16_000, ge=512, le=128_000)

    # --- Paths -------------------------------------------------------------
    config_file: Path = DEFAULT_CONFIG_FILE
    data_file: Path | None = None
    raw_dir: Path = DEFAULT_RAW_DIR
    warehouse_dir: Path = DEFAULT_PROCESSED_DIR
    signals_dir: Path = DEFAULT_SIGNALS_DIR
    vectorstore_dir: Path = DEFAULT_VECTORSTORE_DIR

    # --- Service -----------------------------------------------------------
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: str = "http://localhost:8501"
    api_key: str | None = None

    # --- Behaviour ---------------------------------------------------------
    enforce_scope: bool = True
    enforce_numeric_grounding: bool = True
    log_level: str = "INFO"

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _normalise_provider(cls, value: Any) -> Any:
        if isinstance(value, str):
            cleaned = value.strip().lower()
            return cleaned or "none"
        return value

    @field_validator("data_file", mode="before")
    @classmethod
    def _blank_path_is_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    # -- Derived ------------------------------------------------------------

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins as a list, splitting the comma-separated env value."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def warehouse_path(self) -> Path:
        """Location of the DuckDB file holding every derived table."""
        return self.warehouse_dir / "cardiac.duckdb"

    @property
    def provider_api_key(self) -> str | None:
        """The API key for the configured provider, or ``None`` if unset."""
        env_var = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GOOGLE_API_KEY",
        }.get(self.llm_provider)
        if env_var is None:
            return None
        key = os.environ.get(env_var, "").strip()
        return key or None

    @property
    def llm_available(self) -> bool:
        """True when a narrative model can actually be called.

        When this is False the agent still answers - it falls back to rendering
        the evidence pack through deterministic templates. Nothing about the
        analysis depends on the model being reachable.
        """
        return self.llm_provider != "none" and self.provider_api_key is not None

    def resolve_data_file(self) -> Path:
        """Locate the Cardiac workbook.

        Honours ``CARDIAC_DATA_FILE`` when set, otherwise looks for any of the
        known filenames in ``data/raw``. Raises with an actionable message
        rather than failing deep inside the loader.
        """
        if self.data_file is not None:
            candidate = Path(self.data_file).expanduser()
            if not candidate.is_absolute():
                candidate = (PROJECT_ROOT / candidate).resolve()
            if candidate.exists():
                return candidate
            raise FileNotFoundError(
                f"CARDIAC_DATA_FILE points at {candidate}, which does not exist."
            )

        for name in CANDIDATE_WORKBOOK_NAMES:
            candidate = self.raw_dir / name
            if candidate.exists():
                return candidate

        # Last resort: any .xlsx dropped into data/raw.
        for candidate in sorted(self.raw_dir.glob("*.xlsx")):
            if not candidate.name.startswith("~$"):  # skip Excel lock files
                return candidate

        raise FileNotFoundError(
            "Could not find the Cardiac workbook. Copy it to "
            f"{self.raw_dir / 'cardiac_dataset.xlsx'} or set CARDIAC_DATA_FILE. "
            "See data/raw/README.md."
        )

    def ensure_directories(self) -> None:
        """Create the writable directories the pipeline needs."""
        for directory in (self.raw_dir, self.warehouse_dir, self.vectorstore_dir):
            directory.mkdir(parents=True, exist_ok=True)


class FrameworkConfig(dict):
    """The parsed ``settings.yaml``, with dotted-path lookup.

    Subclassing ``dict`` keeps it trivially serialisable, which matters because
    the exact configuration used for a run is written into every export for
    reproducibility.
    """

    def get_path(self, dotted: str, default: Any = None) -> Any:
        """Read a nested value, e.g. ``get_path("scoring.moi_weights")``."""
        node: Any = self
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def require(self, dotted: str) -> Any:
        """Read a nested value, raising if it is absent."""
        sentinel = object()
        value = self.get_path(dotted, sentinel)
        if value is sentinel:
            raise KeyError(f"Missing required configuration key: {dotted}")
        return value


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()


@functools.lru_cache(maxsize=4)
def _load_framework(path_str: str) -> FrameworkConfig:
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(
            f"Framework configuration not found at {path}. "
            "The repository ships config/settings.yaml; restore it or point "
            "CARDIAC_CONFIG_FILE somewhere valid."
        )
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML mapping at the top level.")
    return FrameworkConfig(payload)


def get_framework(path: Path | None = None) -> FrameworkConfig:
    """Load the prioritisation framework configuration."""
    resolved = path or get_settings().config_file
    return _load_framework(str(resolved))


def reset_config_cache() -> None:
    """Drop cached configuration. Used by tests that patch the environment."""
    get_settings.cache_clear()
    _load_framework.cache_clear()


__all__ = [
    "PROJECT_ROOT",
    "FrameworkConfig",
    "Settings",
    "get_framework",
    "get_settings",
    "reset_config_cache",
]
