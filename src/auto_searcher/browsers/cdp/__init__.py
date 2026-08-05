"""Browser-independent Chrome DevTools Protocol support."""

from .connection import CdpConnection, CdpError
from .endpoint import Endpoint, read_active_endpoint, read_http_endpoint
from .page import CdpPage

__all__ = [
    "CdpConnection",
    "CdpError",
    "Endpoint",
    "read_active_endpoint",
    "read_http_endpoint",
    "CdpPage",
]
