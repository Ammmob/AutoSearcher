import tempfile
import unittest
from datetime import date
from pathlib import Path

from auto_searcher import TopicGather
from auto_searcher.schemas import Topic
from auto_searcher.sources import CachedSource, Source, TencentSource


class StaticSource(Source):
    def __init__(self, name: str, values: list[str]) -> None:
        self._name = name
        self._values = values
        self.fetch_count = 0

    @property
    def name(self) -> str:
        return self._name

    def fetch(self) -> list[Topic]:
        self.fetch_count += 1
        return [Topic(value, self.name) for value in self._values]


class FailingSource(StaticSource):
    def fetch(self) -> list[Topic]:
        raise RuntimeError("offline")


class SourceTests(unittest.TestCase):
    def test_tencent_parser_accepts_empty_payload(self) -> None:
        self.assertEqual(TencentSource().parse({}), [])

    def test_gather_deduplicates_and_isolates_failure(self) -> None:
        gather = TopicGather(
            [FailingSource("bad", []), StaticSource("a", ["Topic", " topic "])]
        )
        self.assertEqual([topic.text for topic in gather.collect()], ["Topic"])

    def test_fallback_is_used_only_when_every_online_source_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fallback_file = Path(directory) / "fallback.txt"
            fallback_file.write_text("fallback topic\n", encoding="utf-8")
            available = TopicGather(
                [StaticSource("online", ["online topic"])], fallback_file
            )
            unavailable = TopicGather([FailingSource("offline", [])], fallback_file)

            self.assertEqual(available.collect()[0].source, "online")
            self.assertEqual(unavailable.collect()[0].source, "fallback")

    def test_gather_stops_when_unique_topics_are_exhausted(self) -> None:
        gather = TopicGather([StaticSource("test", ["one"])])
        self.assertEqual(gather.next_topic().text, "one")
        with self.assertRaises(LookupError):
            gather.next_topic()

    def test_cached_source_reuses_topics_on_the_same_day(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = StaticSource("test", ["today topic"])
            current_day = lambda: date(2026, 8, 4)

            first = CachedSource(source, directory, current_day).fetch()
            source._values = ["changed topic"]
            second = CachedSource(source, directory, current_day).fetch()

            self.assertEqual([topic.text for topic in first], ["today topic"])
            self.assertEqual([topic.text for topic in second], ["today topic"])
            self.assertEqual(source.fetch_count, 1)

    def test_cached_source_refreshes_yesterdays_topics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = StaticSource("test", ["yesterday topic"])
            CachedSource(
                source,
                directory,
                lambda: date(2026, 8, 3),
            ).fetch()
            source._values = ["today topic"]

            topics = CachedSource(
                source,
                directory,
                lambda: date(2026, 8, 4),
            ).fetch()

            self.assertEqual([topic.text for topic in topics], ["today topic"])
            self.assertEqual(source.fetch_count, 2)

    def test_empty_source_result_is_not_cached(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = StaticSource("empty", [])
            cached_source = CachedSource(
                source,
                directory,
                lambda: date(2026, 8, 4),
            )

            cached_source.fetch()
            cached_source.fetch()

            self.assertEqual(source.fetch_count, 2)
            self.assertFalse((Path(directory) / "empty.json").exists())

    def test_corrupt_source_cache_is_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache_file = Path(directory) / "test.json"
            cache_file.write_text("not json", encoding="utf-8")
            source = StaticSource("test", ["fresh topic"])

            topics = CachedSource(
                source,
                directory,
                lambda: date(2026, 8, 4),
            ).fetch()

            self.assertEqual([topic.text for topic in topics], ["fresh topic"])
            self.assertIn('"date": "2026-08-04"', cache_file.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
