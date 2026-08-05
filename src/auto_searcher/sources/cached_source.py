"""HTTP topic source with optional daily caching."""

import json
import logging
import os
from abc import abstractmethod
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import requests

from auto_searcher.schemas import Topic

from .base_source import Source

logger = logging.getLogger(__name__)


class CachedSource(Source):
    """Template-method base class for cached JSON topic APIs."""

    url: str

    def __init__(
        self,
        timeout_seconds: float = 10,
        cache_dir: str | Path | None = None,
        session: requests.Session | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()
        safe_name = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in self.name
        )
        self._cache_file = (
            Path(cache_dir) / f"{safe_name}.json" if cache_dir is not None else None
        )
        self._today = today

    def fetch(self) -> Sequence[Topic]:
        cached = self._load()
        if cached:
            logger.info("数据源 %s 使用今日缓存", self.name)
            return cached

        topics = list(self._fetch_online())
        if topics:
            self._save(topics)
        return topics

    def _fetch_online(self) -> Sequence[Topic]:
        response = self._session.get(
            self.url,
            timeout=self._timeout_seconds,
            headers={"User-Agent": "AutoSearcher/0.1 (+local automation tool)"},
        )
        response.raise_for_status()
        texts = self.parse(response.json())
        return [
            Topic(text=text.strip(), source=self.name, rank=index)
            for index, text in enumerate(texts, start=1)
            if isinstance(text, str) and text.strip()
        ]

    @abstractmethod
    def parse(self, data: Any) -> Sequence[str]:
        raise NotImplementedError

    def _load(self) -> list[Topic]:
        if self._cache_file is None or not self._cache_file.is_file():
            return []
        try:
            payload = json.loads(self._cache_file.read_text(encoding="utf-8"))
            if payload.get("version") != 1:
                return []
            if payload.get("date") != self._today().isoformat():
                logger.info("数据源 %s 的缓存已过期", self.name)
                return []
            if payload.get("source") != self.name:
                return []
            items = payload["topics"]
            if (
                not isinstance(items, list)
                or not items
                or not all(self._valid_topic_data(item) for item in items)
            ):
                return []
            return [
                Topic(
                    text=item["text"],
                    source=item["source"],
                    rank=item.get("rank"),
                )
                for item in items
            ]
        except (OSError, TypeError, ValueError, KeyError) as exc:
            logger.warning("数据源 %s 的缓存读取失败: %s", self.name, exc)
            return []

    def _save(self, topics: Sequence[Topic]) -> None:
        if self._cache_file is None:
            return
        payload = {
            "version": 1,
            "date": self._today().isoformat(),
            "source": self.name,
            "topics": [
                {
                    "text": topic.text,
                    "source": topic.source,
                    "rank": topic.rank,
                }
                for topic in topics
            ],
        }
        temporary_file = self._cache_file.with_name(
            f".{self._cache_file.name}.{os.getpid()}.tmp"
        )
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            temporary_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary_file.replace(self._cache_file)
            logger.info("数据源 %s 已缓存 %d 条话题", self.name, len(topics))
        except OSError as exc:
            logger.warning("数据源 %s 的缓存保存失败: %s", self.name, exc)
        finally:
            try:
                temporary_file.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _valid_topic_data(item: object) -> bool:
        if not isinstance(item, dict):
            return False
        rank = item.get("rank")
        return (
            isinstance(item.get("text"), str)
            and bool(item["text"].strip())
            and isinstance(item.get("source"), str)
            and bool(item["source"].strip())
            and (rank is None or isinstance(rank, int))
        )
