"""Resolve paths consistently in source and packaged executions."""

import os
import sys
from pathlib import Path


class PathResolutionError(ValueError):
    pass


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        if (parent / "pyproject.toml").is_file() and (
            parent / "src" / "auto_searcher"
        ).is_dir():
            return parent
    return Path.cwd().resolve()


def default_config_path() -> Path:
    portable_config = application_dir() / "config" / "config.yaml"
    if not getattr(sys, "frozen", False) or portable_config.is_file():
        return portable_config

    app_data = os.environ.get("APPDATA")
    if app_data:
        installed_config = Path(app_data) / "AutoSearcher" / "config.yaml"
        if installed_config.is_file():
            return installed_config.resolve()
    return portable_config


def default_edge_user_data_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise PathResolutionError("环境变量 LOCALAPPDATA 不存在，无法定位 Edge 用户目录")
    return (
        Path(local_app_data).expanduser() / "Microsoft" / "Edge" / "User Data"
    ).resolve()


def default_topic_cache_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise PathResolutionError("环境变量 LOCALAPPDATA 不存在，无法定位话题缓存")
    return (
        Path(local_app_data).expanduser()
        / "AutoSearcher"
        / "cache"
        / "sources"
    ).resolve()


def resolve_configured_path(value: str | Path, base_dir: Path) -> Path:
    expanded = Path(os.path.expandvars(str(value))).expanduser()
    if not expanded.is_absolute():
        expanded = base_dir / expanded
    return expanded.resolve()
