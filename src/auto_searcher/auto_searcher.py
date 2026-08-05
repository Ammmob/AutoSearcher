"""Coordinates topic selection and browser searching."""

import logging
import random
import threading
import time
from collections.abc import Callable

from auto_searcher.browsers import Browser
from auto_searcher.schemas import RunSummary, SearchConfig, SearchResult
from auto_searcher.topic_gather import TopicGather

logger = logging.getLogger(__name__)


class AutoSearcher:
    """Coordinates topic gathering and browser searching."""

    def __init__(
        self,
        browser: Browser,
        topic_gather: TopicGather,
        config: SearchConfig,
        stop_event: threading.Event | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
    ) -> None:
        self._browser = browser
        self._topic_gather = topic_gather
        self._config = config
        self._stop_event = stop_event or threading.Event()
        self._sleep = sleeper
        self._clock = clock
        self._rng = rng or random.Random()

    def run(self) -> RunSummary:
        summary = RunSummary(requested=self._config.count)
        with self._browser:
            for index in range(self._config.count):
                if self._stop_event.is_set():
                    summary.stopped = True
                    break
                try:
                    topic = self._topic_gather.next_topic()
                except LookupError as exc:
                    logger.error("无法继续搜索: %s", exc)
                    break

                logger.info(
                    "搜索 %d/%d: %s（来源: %s）",
                    index + 1,
                    self._config.count,
                    topic.text,
                    topic.source,
                )
                started = self._clock()
                try:
                    self._browser.search(topic.text)
                    self._browser.browse_results()
                    result = SearchResult(topic, True, self._clock() - started)
                except Exception as exc:
                    logger.exception("搜索失败: %s", topic.text)
                    result = SearchResult(
                        topic,
                        False,
                        self._clock() - started,
                        str(exc),
                    )
                summary.results.append(result)

                if index < self._config.count - 1 and not self._stop_event.is_set():
                    self._sleep(self._rng.uniform(*self._config.interval_seconds))
        return summary
