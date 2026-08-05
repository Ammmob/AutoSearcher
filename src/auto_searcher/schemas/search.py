"""Search-related data structures."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Topic:
    text: str
    source: str
    rank: int | None = None


@dataclass(frozen=True, slots=True)
class SearchResult:
    topic: Topic
    success: bool
    elapsed_seconds: float
    error: str | None = None


@dataclass(slots=True)
class RunSummary:
    requested: int
    results: list[SearchResult] = field(default_factory=list)
    stopped: bool = False

    @property
    def succeeded(self) -> int:
        return sum(result.success for result in self.results)

    @property
    def failed(self) -> int:
        return len(self.results) - self.succeeded
