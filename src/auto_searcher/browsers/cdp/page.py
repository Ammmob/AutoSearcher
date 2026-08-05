"""Page-level operations implemented with the Chrome DevTools Protocol."""

import time
from collections.abc import Callable
from typing import Any

from .connection import CdpConnection, CdpError


class CdpPage:
    def __init__(
        self,
        connection: CdpConnection,
        target_id: str,
        session_id: str,
        timeout_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._connection = connection
        self.target_id = target_id
        self.session_id = session_id
        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._sleep = sleeper

    def prepare(self, script: str) -> None:
        self.command("Page.enable")
        self.command("Runtime.enable")
        self.command(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": script},
        )

    def navigate(self, url: str) -> None:
        result = self.command("Page.navigate", {"url": url})
        if result.get("errorText"):
            raise CdpError(f"页面加载失败: {result['errorText']}")
        self.wait_for_value(
            "document.readyState === 'complete' ? true : null",
            "等待页面加载超时",
        )

    def activate(self) -> None:
        self._connection.command(
            "Target.activateTarget",
            {"targetId": self.target_id},
        )
        self.evaluate("window.focus(); true")

    def close(self) -> None:
        self._connection.command(
            "Target.closeTarget",
            {"targetId": self.target_id},
        )

    def command(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._connection.command(method, params, self.session_id)

    def evaluate(self, expression: str) -> Any:
        result = self.command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
                "userGesture": True,
            },
        )
        if result.get("exceptionDetails"):
            description = result["exceptionDetails"].get("text", "JavaScript error")
            raise CdpError(f"页面脚本执行失败: {description}")
        remote_object = result.get("result")
        if not isinstance(remote_object, dict):
            raise CdpError("Runtime.evaluate 返回了无效结果")
        return remote_object.get("value")

    def wait_for_value(self, expression: str, timeout_message: str) -> Any:
        deadline = self._clock() + self._timeout_seconds
        last_error: CdpError | None = None
        while self._clock() < deadline:
            try:
                value = self.evaluate(expression)
            except CdpError as exc:
                last_error = exc
                self._sleep(0.1)
                continue
            if value is not None and value is not False:
                return value
            self._sleep(0.1)
        if last_error is not None:
            raise CdpError(f"{timeout_message}: {last_error}") from last_error
        raise CdpError(timeout_message)
