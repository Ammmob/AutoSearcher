"""Browser abstractions and implementations."""

from .search_interaction import SearchInteraction
from .base_browser import Browser, SearchBrowser
from .edge_browser import EdgeBrowser

__all__ = [
    "Browser",
    "SearchInteraction",
    "SearchBrowser",
    "EdgeBrowser",
]
