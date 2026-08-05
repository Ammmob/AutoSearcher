import math
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from auto_searcher.schemas import AppConfig, BrowserConfig, SearchConfig, SourcesConfig
from auto_searcher.utils.path_utils import (
    PathResolutionError,
    default_topic_cache_dir,
    resolve_configured_path,
)


class ConfigError(ValueError):
    pass


def _range_pair(
    value: Any, name: str, cast: type[int] | type[float]
) -> tuple[Any, Any]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ConfigError(f"{name} 必须是包含两个数字的列表")
    try:
        low, high = cast(value[0]), cast(value[1])
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} 必须只包含有效数字") from exc
    if any(
        isinstance(number, float) and not math.isfinite(number)
        for number in (low, high)
    ):
        raise ConfigError(f"{name} 必须只包含有限数字")
    if low < 0 or high < low:
        raise ConfigError(f"{name} 必须满足 0 <= 最小值 <= 最大值")
    return low, high


def _positive_float(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} 必须是有效数字") from exc
    if not math.isfinite(number) or number <= 0:
        raise ConfigError(f"{name} 必须是大于 0 的有限数字")
    return number


def load_config(path: str | Path) -> AppConfig:
    config_path = resolve_configured_path(path, Path.cwd())
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"无法读取配置 {config_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("配置文件根节点必须是对象")

    browser_raw = raw.get("browser", {})
    search_raw = raw.get("search", {})
    sources_raw = raw.get("sources", {})
    config_sections = (browser_raw, search_raw, sources_raw)
    if not all(isinstance(item, dict) for item in config_sections):
        raise ConfigError("browser、search、sources 必须是对象")

    try:
        count = int(search_raw.get("count", 30))
    except (TypeError, ValueError) as exc:
        raise ConfigError("search.count 必须是有效整数") from exc
    if count <= 0:
        raise ConfigError("search.count 必须大于 0")

    browser_type = str(browser_raw.get("type", "edge")).lower()
    if browser_type != "edge":
        raise ConfigError(f"暂不支持浏览器类型: {browser_type}")

    args_raw = browser_raw.get("args", [])
    if not isinstance(args_raw, list):
        raise ConfigError("browser.args 必须是字符串列表")
    browser_args: list[str] = []
    for value in args_raw:
        if not isinstance(value, str) or not value.strip():
            raise ConfigError("browser.args 必须只包含非空字符串")
        argument = os.path.expandvars(value.strip())
        if argument.casefold() == "--remote-debugging-port":
            raise ConfigError(
                "调试端口必须写成 --remote-debugging-port=<端口号>"
            )
        browser_args.append(argument)

    browser = BrowserConfig(
        type=browser_type,
        args=tuple(browser_args),
        page_timeout_seconds=_positive_float(
            browser_raw.get("page_timeout_seconds", 20),
            "browser.page_timeout_seconds",
        ),
    )

    search_url = str(search_raw.get("url", "https://www.bing.com")).strip()
    parsed_search_url = urlparse(search_url)
    if parsed_search_url.scheme not in {"http", "https"}:
        raise ConfigError("search.url 必须是有效的 HTTP/HTTPS 地址")
    if not parsed_search_url.netloc:
        raise ConfigError("search.url 必须包含有效的域名")

    search = SearchConfig(
        url=search_url,
        count=count,
        interval_seconds=_range_pair(
            search_raw.get("interval_seconds", [3, 5]), "search.interval_seconds", float
        ),
        typing_delay_seconds=_range_pair(
            search_raw.get("typing_delay_seconds", [0.08, 0.2]),
            "search.typing_delay_seconds",
            float,
        ),
        scroll_count=_range_pair(
            search_raw.get("scroll_count", [3, 6]), "search.scroll_count", int
        ),
        scroll_pause_seconds=_range_pair(
            search_raw.get("scroll_pause_seconds", [1.5, 3]),
            "search.scroll_pause_seconds",
            float,
        ),
    )

    enabled = sources_raw.get(
        "enabled",
        ["baidu", "tencent", "toutiao"],
    )
    if not isinstance(enabled, list) or not enabled:
        raise ConfigError("sources.enabled 必须是非空列表")
    cache_dir = sources_raw.get("cache_dir")
    try:
        if cache_dir:
            cache_path = resolve_configured_path(
                cache_dir,
                config_path.parent,
            )
        else:
            cache_path = default_topic_cache_dir()
    except PathResolutionError as exc:
        raise ConfigError(str(exc)) from exc
    fallback_file = sources_raw.get("fallback_file")
    if fallback_file:
        fallback_path = resolve_configured_path(
            fallback_file,
            config_path.parent,
        )
        if not fallback_path.is_file():
            raise ConfigError(f"保险话题文件不存在: {fallback_path}")
        fallback_file = str(fallback_path)
    sources = SourcesConfig(
        enabled=tuple(str(name).lower() for name in enabled),
        request_timeout_seconds=_positive_float(
            sources_raw.get("request_timeout_seconds", 10),
            "sources.request_timeout_seconds",
        ),
        cache_dir=str(cache_path),
        fallback_file=fallback_file,
    )

    return AppConfig(browser=browser, search=search, sources=sources)
