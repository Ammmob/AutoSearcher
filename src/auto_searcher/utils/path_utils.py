"""Resolve paths consistently in source and packaged executions."""

import json
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


def detect_edge_profile_name(user_data_dir: Path) -> str:
    """Return Edge's most recently used profile, or ``Default`` as a fallback."""
    local_state_path = user_data_dir / "Local State"
    try:
        local_state = json.loads(local_state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "Default"

    profile_state = local_state.get("profile")
    if not isinstance(profile_state, dict):
        return "Default"

    candidates = [profile_state.get("last_used")]
    last_active_profiles = profile_state.get("last_active_profiles")
    if isinstance(last_active_profiles, list):
        candidates.extend(last_active_profiles)

    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        profile_name = candidate.strip()
        if Path(profile_name).name != profile_name:
            continue
        if (user_data_dir / profile_name).is_dir():
            return profile_name
    return "Default"


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
