"""Daily on-disk cache wrapper for topic sources."""

import json
import logging
import os
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

from auto_searcher.schemas import Topic

from .base_source import Source

logger = logging.getLogger(__name__)


class CachedSource(Source):
    """Adds an independent daily cache to another source."""

    def __init__(
        self,
        source: Source,
        cache_dir: str | Path,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._source = source
        safe_name = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in source.name
        )
        self._cache_file = Path(cache_dir) / f"{safe_name}.json"
        self._today = today

    @property
    def name(self) -> str:
        return self._source.name

    def fetch(self) -> Sequence[Topic]:
        cached = self._load()
        if cached:
            logger.info("数据源 %s 使用今日缓存", self.name)
            return cached

        topics = list(self._source.fetch())
        if topics:
            self._save(topics)
        return topics

    def _load(self) -> list[Topic]:
        if not self._cache_file.is_file():
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
