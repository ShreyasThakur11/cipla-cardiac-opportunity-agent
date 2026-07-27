"""HTTP service.

Exposes the agent and the underlying analytics so the Streamlit console, a
notebook, or anything else can consume them over the network. The API is
deliberately thin: it validates input, calls the same functions the CLI calls,
and serialises the result.
"""

from .main import app, create_app

__all__ = ["app", "create_app"]
