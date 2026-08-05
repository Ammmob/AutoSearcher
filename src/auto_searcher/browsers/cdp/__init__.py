"""Low-level Chrome DevTools Protocol support for Edge."""

from .connection import CdpConnection, CdpError
from .endpoint import EdgeEndpoint, read_edge_endpoint
from .page import CdpPage
from .search_interaction import CdpSearchInteraction
from .edge_browser import CdpEdgeBrowser

__all__ = [
    "CdpConnection",
    "CdpError",
    "EdgeEndpoint",
    "read_edge_endpoint",
    "CdpPage",
    "CdpSearchInteraction",
    "CdpEdgeBrowser",
]
