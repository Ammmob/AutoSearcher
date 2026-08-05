"""High-level browser abstractions and implementations."""

from .browser import Browser
from .chromium_browser import ChromiumBrowser
from .edge_browser import EdgeBrowser

__all__ = [
    "Browser",
    "ChromiumBrowser",
    "EdgeBrowser",
]
