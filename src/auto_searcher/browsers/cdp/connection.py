"""Small synchronous client for the Chrome DevTools Protocol."""

import json
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import websocket


class CdpError(RuntimeError):
    pass


class CdpConnection:
    def __init__(
        self,
        websocket_url: str,
        timeout_seconds: float,
        connector: Callable[..., websocket.WebSocket] = websocket.create_connection,
    ) -> None:
        self._websocket_url = websocket_url
        self._timeout_seconds = timeout_seconds
        self._connector = connector
        self._socket: websocket.WebSocket | None = None
        self._next_id = 1
        self._events: deque[dict[str, Any]] = deque()

    def open(self) -> None:
        if self._socket is not None:
            return
        try:
            self._socket = self._connector(
                self._websocket_url,
                timeout=self._timeout_seconds,
                suppress_origin=True,
            )
        except (OSError, websocket.WebSocketException) as exc:
            raise CdpError(f"无法连接浏览器 DevTools WebSocket: {exc}") from exc

    def close(self) -> None:
        if self._socket is None:
            return
        try:
            self._socket.close()
        finally:
            self._socket = None
            self._events.clear()

    def command(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        message: dict[str, Any] = {
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        if session_id:
            message["sessionId"] = session_id
        self._send(message)

        deadline = time.monotonic() + self._timeout_seconds
        while True:
            response = self._receive(deadline)
            if response.get("id") != request_id:
                self._events.append(response)
                continue
            error = response.get("error")
            if isinstance(error, dict):
                detail = error.get("message") or error
                raise CdpError(f"CDP 命令 {method} 失败: {detail}")
            result = response.get("result", {})
            if not isinstance(result, dict):
                raise CdpError(f"CDP 命令 {method} 返回了无效结果")
            return result

    def wait_for_event(
        self,
        method: str,
        session_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        for event in tuple(self._events):
            if self._matches_event(event, method, session_id):
                self._events.remove(event)
                return event

        timeout = timeout_seconds or self._timeout_seconds
        deadline = time.monotonic() + timeout
        while True:
            event = self._receive(deadline)
            if self._matches_event(event, method, session_id):
                return event
            self._events.append(event)

    def _send(self, message: dict[str, Any]) -> None:
        if self._socket is None:
            raise CdpError("CDP 连接尚未打开")
        try:
            self._socket.send(json.dumps(message, ensure_ascii=False))
        except (OSError, websocket.WebSocketException) as exc:
            raise CdpError(f"发送 CDP 命令失败: {exc}") from exc

    def _receive(self, deadline: float) -> dict[str, Any]:
        if self._socket is None:
            raise CdpError("CDP 连接尚未打开")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CdpError("等待 CDP 响应超时")
        try:
            self._socket.settimeout(remaining)
            raw_message = self._socket.recv()
        except (OSError, websocket.WebSocketException) as exc:
            raise CdpError(f"接收 CDP 响应失败: {exc}") from exc
        if not isinstance(raw_message, str):
            raise CdpError("浏览器返回了非文本 CDP 消息")
        try:
            message = json.loads(raw_message)
        except json.JSONDecodeError as exc:
            raise CdpError("浏览器返回了无效的 CDP JSON") from exc
        if not isinstance(message, dict):
            raise CdpError("浏览器返回了无效的 CDP 消息")
        return message

    @staticmethod
    def _matches_event(
        message: dict[str, Any],
        method: str,
        session_id: str | None,
    ) -> bool:
        return message.get("method") == method and (
            session_id is None or message.get("sessionId") == session_id
        )
