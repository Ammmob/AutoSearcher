import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from auto_searcher.browsers.cdp import (
    CdpConnection,
    CdpError,
    CdpPage,
    Endpoint,
    read_active_endpoint,
    read_http_endpoint,
)
from auto_searcher.browsers.backend import CdpBackend
from auto_searcher.browsers.interaction import CdpInteraction, Interaction
from auto_searcher.schemas import BrowserConfig, SearchConfig


class CdpConnectionTests(unittest.TestCase):
    def test_command_matches_response_and_preserves_events(self) -> None:
        socket = Mock()
        socket.recv.side_effect = [
            json.dumps({"method": "Page.loadEventFired", "params": {}}),
            json.dumps({"id": 1, "result": {"product": "Edg/151"}}),
        ]
        connection = CdpConnection(
            "ws://127.0.0.1:9222/devtools/browser/test",
            1,
            connector=Mock(return_value=socket),
        )
        connection.open()

        result = connection.command("Browser.getVersion")
        event = connection.wait_for_event("Page.loadEventFired")

        self.assertEqual(result, {"product": "Edg/151"})
        self.assertEqual(event["method"], "Page.loadEventFired")
        request = json.loads(socket.send.call_args.args[0])
        self.assertEqual(request["method"], "Browser.getVersion")

    def test_command_reports_protocol_error(self) -> None:
        socket = Mock()
        socket.recv.return_value = json.dumps(
            {"id": 1, "error": {"message": "Unknown method"}}
        )
        connection = CdpConnection(
            "ws://127.0.0.1:9222/devtools/browser/test",
            1,
            connector=Mock(return_value=socket),
        )
        connection.open()

        with self.assertRaisesRegex(CdpError, "Unknown method"):
            connection.command("Missing.command")


class CdpPageTests(unittest.TestCase):
    def test_wait_retries_during_navigation_context_replacement(self) -> None:
        connection = Mock()
        connection.command.side_effect = [
            CdpError("execution context was destroyed"),
            {"result": {"value": True}},
        ]
        clock = Mock(side_effect=[0.0, 0.1, 0.2])
        page = CdpPage(
            connection,
            "target-1",
            "session-1",
            1,
            clock=clock,
            sleeper=lambda _: None,
        )

        self.assertTrue(page.wait_for_value("document.readyState", "timeout"))


class EndpointTests(unittest.TestCase):
    @patch("auto_searcher.browsers.cdp.endpoint.http.client.HTTPConnection")
    def test_reads_classic_http_websocket_endpoint(self, connection_type) -> None:
        response = connection_type.return_value.getresponse.return_value
        response.status = 200
        response.read.return_value = json.dumps(
            {
                "Browser": "Edg/131.0",
                "webSocketDebuggerUrl": (
                    "ws://127.0.0.1:9222/devtools/browser/browser-id"
                ),
            }
        ).encode("utf-8")

        endpoint = read_http_endpoint("127.0.0.1:9222")

        self.assertEqual(
            endpoint,
            Endpoint(
                "127.0.0.1:9222",
                "ws://127.0.0.1:9222/devtools/browser/browser-id",
            ),
        )

    def test_reads_browser_websocket_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            user_data_dir = Path(temp_dir)
            (user_data_dir / "DevToolsActivePort").write_text(
                "9222\n/devtools/browser/browser-id\n",
                encoding="utf-8",
            )

            endpoint = read_active_endpoint(user_data_dir)

        self.assertEqual(
            endpoint,
            Endpoint(
                "127.0.0.1:9222",
                "ws://127.0.0.1:9222/devtools/browser/browser-id",
            ),
        )

    def test_rejects_stale_endpoint_for_different_explicit_port(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            user_data_dir = Path(temp_dir)
            (user_data_dir / "DevToolsActivePort").write_text(
                "3761\n/devtools/browser/old-id\n",
                encoding="utf-8",
            )

            endpoint = read_active_endpoint(
                user_data_dir,
                expected_address="127.0.0.1:9222",
            )

        self.assertIsNone(endpoint)

    def test_rejects_page_level_websocket_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            user_data_dir = Path(temp_dir)
            (user_data_dir / "DevToolsActivePort").write_text(
                "9222\n/devtools/page/page-id\n",
                encoding="utf-8",
            )

            self.assertIsNone(read_active_endpoint(user_data_dir))


class CdpBackendTests(unittest.TestCase):
    @patch("auto_searcher.browsers.backend.CdpPage")
    def test_open_creates_and_prepares_an_isolated_tab(self, cdp_page) -> None:
        connection = Mock()
        connection.command.side_effect = [
            {"product": "Edg/151.0"},
            {"targetId": "target-1"},
            {"sessionId": "session-1"},
        ]
        page = cdp_page.return_value
        backend = CdpBackend(
            Endpoint(
                "127.0.0.1:9222",
                "ws://127.0.0.1:9222/devtools/browser/test",
            ),
            SearchConfig(),
            BrowserConfig().page_timeout_seconds,
            connection=connection,
            interaction=Mock(),
        )

        backend.open()

        connection.open.assert_called_once_with()
        connection.command.assert_any_call("Browser.getVersion")
        connection.command.assert_any_call(
            "Target.createTarget",
            {"url": "about:blank", "newWindow": False},
        )
        connection.command.assert_any_call(
            "Target.attachToTarget",
            {"targetId": "target-1", "flatten": True},
        )
        page.prepare.assert_called_once()
        page.navigate.assert_called_once_with("https://www.bing.com")
        page.activate.assert_called_once_with()

    @patch("auto_searcher.browsers.backend.CdpPage")
    def test_owned_browser_closes_the_whole_instance(self, cdp_page) -> None:
        connection = Mock()
        connection.command.side_effect = [
            {"product": "Chrome/151.0"},
            {"targetId": "target-1"},
            {"sessionId": "session-1"},
            {},
        ]
        backend = CdpBackend(
            Endpoint(
                "127.0.0.1:9222",
                "ws://127.0.0.1:9222/devtools/browser/test",
            ),
            SearchConfig(),
            BrowserConfig().page_timeout_seconds,
            owns_browser=True,
            connection=connection,
            interaction=Mock(),
        )
        backend.open()

        backend.close()

        connection.command.assert_called_with("Browser.close")
        cdp_page.return_value.close.assert_not_called()


class FakeCdpPage:
    def __init__(self) -> None:
        self.commands: list[tuple[str, dict[str, object]]] = []
        self.scroll_y = 0

    def evaluate(self, expression: str) -> object:
        if expression == "location.href":
            return "https://www.bing.com/"
        if expression in {
            CdpInteraction.SEARCH_BOX_FOCUSED_EXPRESSION,
            CdpInteraction.SEARCH_BOX_EMPTY_EXPRESSION,
        }:
            return True
        return {
            "height": 1800,
            "viewport": 800,
            "width": 1200,
            "y": self.scroll_y,
        }

    def wait_for_value(self, expression: str, timeout_message: str) -> object:
        if expression == CdpInteraction.SEARCH_BOX_EXPRESSION:
            return {"x": 300, "y": 100}
        return "https://www.bing.com/search?q=test"

    def command(
        self,
        method: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        command_params = params or {}
        self.commands.append((method, command_params))
        if method == "Input.dispatchMouseEvent":
            delta_y = command_params.get("deltaY")
            if isinstance(delta_y, int):
                self.scroll_y = max(0, self.scroll_y + delta_y)
        return {}


class CdpInteractionTests(unittest.TestCase):
    def test_implementation_inherits_interface(self) -> None:
        self.assertTrue(issubclass(CdpInteraction, Interaction))

    def test_consecutive_searches_restore_search_box_before_selecting(self) -> None:
        page = FakeCdpPage()
        interaction = CdpInteraction(
            page,
            SearchConfig(),
            sleeper=lambda _: None,
        )

        interaction.search("测试")
        page.scroll_y = 900
        interaction.search("新闻")

        methods = [method for method, _params in page.commands]
        inserted_text = [
            params["text"]
            for method, params in page.commands
            if method == "Input.insertText"
        ]
        self.assertIn("Input.dispatchMouseEvent", methods)
        self.assertIn("Input.dispatchKeyEvent", methods)
        self.assertEqual(inserted_text, ["测", "试", "新", "闻"])
        upward_scrolls = [
            params["deltaY"]
            for method, params in page.commands
            if method == "Input.dispatchMouseEvent"
            and isinstance(params.get("deltaY"), int)
            and params["deltaY"] < 0
        ]
        self.assertTrue(upward_scrolls)
        select_all_events = [
            params
            for method, params in page.commands
            if method == "Input.dispatchKeyEvent"
            and params.get("key") == "a"
            and params.get("type") == "rawKeyDown"
        ]
        self.assertEqual(len(select_all_events), 2)
        self.assertTrue(all("commands" not in event for event in select_all_events))


if __name__ == "__main__":
    unittest.main()
