"""High-level browser abstractions."""

import logging
from abc import ABC, abstractmethod
from types import TracebackType

from .backend import Backend

logger = logging.getLogger(__name__)


class Browser(ABC):
    def __init__(self, backend: Backend) -> None:
        self._backend = backend

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    def open(self) -> None:
        self._backend.open()

    def search(self, keyword: str) -> None:
        self._backend.search(keyword)

    def browse_results(self) -> None:
        self._backend.browse_results()

    def close(self) -> None:
        self._backend.close()

    def __enter__(self) -> "Browser":
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class EdgeBrowser(Browser):
    @property
    def name(self) -> str:
        return "Edge"

    def open(self) -> None:
        logger.info("使用浏览器: %s", self.name)
        super().open()
