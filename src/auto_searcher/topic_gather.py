import logging
import random
from collections.abc import Sequence
from pathlib import Path

from auto_searcher.schemas import Topic
from auto_searcher.sources import Source

logger = logging.getLogger(__name__)


class TopicGather:
    """Collects online sources and uses fallback data only when all are unavailable."""

    def __init__(
        self,
        online_sources: Sequence[Source],
        fallback_file: str | Path | None = None,
        rng: random.Random | None = None,
    ) -> None:
        if not online_sources:
            raise ValueError("至少需要一个在线数据源")
        self._online_sources = tuple(online_sources)
        self._fallback_file = Path(fallback_file) if fallback_file else None
        self._rng = rng or random.Random()
        self._remaining: list[Topic] | None = None

    def next_topic(self) -> Topic:
        """Return each collected topic once, in random order."""

        if self._remaining is None:
            self._remaining = self.collect()
            self._rng.shuffle(self._remaining)
        if not self._remaining:
            raise LookupError("可用话题已经耗尽")
        return self._remaining.pop()

    def collect(self) -> list[Topic]:
        collected: list[Topic] = []
        for source in self._online_sources:
            try:
                topics = source.fetch()
                collected.extend(topics)
                logger.info("数据源 %s 返回 %d 条话题", source.name, len(topics))
            except Exception as exc:
                logger.warning("数据源 %s 获取失败: %s", source.name, exc)

        unique = self._deduplicate(collected)
        if unique:
            return unique

        fallback = self._deduplicate(self._load_fallback_topics())
        if fallback:
            logger.warning("所有在线数据源均无结果，启用 %d 条保险话题", len(fallback))
        return fallback

    def _load_fallback_topics(self) -> list[Topic]:
        if self._fallback_file is None:
            return []
        lines = self._fallback_file.read_text(encoding="utf-8").splitlines()
        return [
            Topic(text=text, source="fallback", rank=index)
            for index, line in enumerate(lines, start=1)
            if (text := line.strip()) and not text.startswith("#")
        ]

    @staticmethod
    def _deduplicate(topics: Sequence[Topic]) -> list[Topic]:
        unique: dict[str, Topic] = {}
        for topic in topics:
            key = " ".join(topic.text.split()).casefold()
            if key:
                unique.setdefault(key, topic)
        return list(unique.values())
