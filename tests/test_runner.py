import unittest

from auto_searcher import AutoSearcher, TopicGather
from auto_searcher.browsers import Browser
from auto_searcher.schemas import SearchConfig, Topic
from auto_searcher.sources import Source


class StaticSource(Source):
    @property
    def name(self) -> str:
        return "test"

    def fetch(self) -> list[Topic]:
        return [Topic("first", self.name), Topic("second", self.name)]


class FakeBrowser(Browser):
    def __init__(self) -> None:
        self.opened = False
        self.closed = False
        self.searched: list[str] = []

    def open(self) -> None:
        self.opened = True

    def search(self, keyword: str) -> None:
        self.searched.append(keyword)

    def browse_results(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class RunnerTests(unittest.TestCase):
    def test_runner_can_be_tested_without_real_browser_or_network(self) -> None:
        browser = FakeBrowser()
        config = SearchConfig(count=2, interval_seconds=(0, 0))
        searcher = AutoSearcher(
            browser,
            TopicGather([StaticSource()]),
            config,
            sleeper=lambda _: None,
            clock=lambda: 1.0,
        )
        summary = searcher.run()

        self.assertTrue(browser.opened)
        self.assertTrue(browser.closed)
        self.assertEqual(set(browser.searched), {"first", "second"})
        self.assertEqual(summary.succeeded, 2)


if __name__ == "__main__":
    unittest.main()
