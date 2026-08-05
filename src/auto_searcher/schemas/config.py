"""Configuration data structures."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BrowserConfig:
    type: str = "edge"
    user_data_dir: str | None = None
    profile_name: str | None = None
    debugger_address: str | None = None
    auto_detect_debugger: bool = False
    page_timeout_seconds: float = 20.0


@dataclass(frozen=True, slots=True)
class SearchConfig:
    url: str = "https://www.bing.com"
    count: int = 30
    interval_seconds: tuple[float, float] = (3.0, 5.0)
    typing_delay_seconds: tuple[float, float] = (0.08, 0.2)
    scroll_count: tuple[int, int] = (3, 6)
    scroll_pause_seconds: tuple[float, float] = (1.5, 3.0)


@dataclass(frozen=True, slots=True)
class SourcesConfig:
    enabled: tuple[str, ...] = ("baidu", "tencent", "toutiao")
    request_timeout_seconds: float = 10.0
    cache_dir: str | None = None
    fallback_file: str | None = None


@dataclass(frozen=True, slots=True)
class AppConfig:
    browser: BrowserConfig
    search: SearchConfig
    sources: SourcesConfig
