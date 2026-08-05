"""Command-line entry point for AutoSearcher."""

import argparse
import logging
import signal
import threading
from collections.abc import Callable
from pathlib import Path

from auto_searcher import AutoSearcher, TopicGather
from auto_searcher.browsers import Browser, EdgeBrowser
from auto_searcher.schemas import AppConfig
from auto_searcher.sources import (
    Source,
    BaiduSource,
    CachedSource,
    TencentSource,
    ToutiaoSource,
)
from auto_searcher.utils.config_utils import ConfigError, load_config
from auto_searcher.utils.path_utils import default_config_path, resolve_configured_path

DEFAULT_CONFIG = default_config_path()


def _build_topic_gather(config: AppConfig, only: str | None = None) -> TopicGather:
    timeout = config.sources.request_timeout_seconds
    sources: dict[str, Callable[[], Source]] = {
        "baidu": lambda: BaiduSource(timeout),
        "tencent": lambda: TencentSource(timeout),
        "toutiao": lambda: ToutiaoSource(timeout),
    }
    names = (only,) if only else config.sources.enabled
    unknown = [name for name in names if name not in sources]
    if unknown:
        available = ", ".join(sorted(sources))
        raise ValueError(f"未知数据源 {unknown}；可用数据源: {available}")

    online_sources = [sources[name]() for name in names]
    if not only and config.sources.cache_dir:
        online_sources = [
            CachedSource(source, config.sources.cache_dir)
            for source in online_sources
        ]
    return TopicGather(
        online_sources=online_sources,
        fallback_file=None if only else config.sources.fallback_file,
    )


def _build_browser(config: AppConfig) -> Browser:
    if config.browser.type == "edge":
        return EdgeBrowser(config.browser, config.search)
    raise ValueError(f"没有注册浏览器实现: {config.browser.type}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="使用热点关键词进行网页自动搜索")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="YAML 配置文件路径")
    parser.add_argument("--verbose", action="store_true", help="输出调试日志")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("run", "check", "topics"),
        default="run",
        help="执行命令：完整搜索、检查配置或获取话题（默认: run）",
    )
    parser.add_argument("--source", help="topics 命令仅调试指定数据源")
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="topics 命令最多显示多少条",
    )
    return parser


def _install_signal_handlers(stop_event: threading.Event) -> None:
    def stop(_signum: int, _frame: object) -> None:
        logging.getLogger(__name__).info("收到退出信号，将在当前步骤结束后停止")
        stop_event.set()

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    try:
        config = load_config(args.config)
        if args.command == "check":
            config_path = resolve_configured_path(args.config, Path.cwd())
            print(f"配置有效: {config_path}")
            print(f"Edge 用户目录: {config.browser.user_data_dir}")
            print(f"Edge 配置文件: {config.browser.profile_name}")
            debugger_address = config.browser.debugger_address
            if config.browser.auto_detect_debugger and config.browser.user_data_dir:
                cdp_endpoint = EdgeBrowser.detect_endpoint(config.browser)
                if cdp_endpoint is not None:
                    debugger_address = f"{cdp_endpoint.address}（CDP WebSocket）"
                debugger_address = debugger_address or "自动检测（当前未发现）"
            elif debugger_address is None:
                debugger_address = "已禁用"
            print(f"远程调试地址: {debugger_address}")
            print(f"数据源缓存目录: {config.sources.cache_dir}")
            return 0

        topic_gather = _build_topic_gather(config, args.source)
        if args.command == "topics":
            topics = topic_gather.collect()
            for topic in topics[: max(args.limit, 0)]:
                rank = f"#{topic.rank}" if topic.rank else "-"
                print(f"{topic.source:8} {rank:4} {topic.text}")
            print(f"共获取 {len(topics)} 条去重话题")
            return 0 if topics else 2

        stop_event = threading.Event()
        _install_signal_handlers(stop_event)
        searcher = AutoSearcher(
            _build_browser(config), topic_gather, config.search, stop_event
        )
        summary = searcher.run()
        print(
            f"运行结束：成功 {summary.succeeded}，失败 {summary.failed}，"
            f"完成 {len(summary.results)}/{summary.requested}"
        )
        return 0 if summary.failed == 0 else 1
    except (ConfigError, ValueError, RuntimeError) as exc:
        logging.getLogger(__name__).error("%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
