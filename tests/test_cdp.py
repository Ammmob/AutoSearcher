import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from auto_searcher.browsers.cdp import (
    CdpConnection,
    CdpError,
    CdpPage,
    EdgeEndpoint,
    read_edge_endpoint,
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


class EdgeEndpointTests(unittest.TestCase):
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
            EdgeEndpoint(
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

            endpoint = read_edge_endpoint(user_data_dir)

        self.assertEqual(
            endpoint,
            EdgeEndpoint(
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

            endpoint = read_edge_endpoint(
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

            self.assertIsNone(read_edge_endpoint(user_data_dir))


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
            BrowserConfig(),
            SearchConfig(),
            endpoint=EdgeEndpoint(
                "127.0.0.1:9222",
                "ws://127.0.0.1:9222/devtools/browser/test",
            ),
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
    def test_owned_browser_closes_the_whole_edge_instance(self, cdp_page) -> None:
        connection = Mock()
        connection.command.side_effect = [
            {"product": "Edg/151.0"},
            {"targetId": "target-1"},
            {"sessionId": "session-1"},
            {},
        ]
        backend = CdpBackend(
            BrowserConfig(),
            SearchConfig(),
            endpoint=EdgeEndpoint(
                "127.0.0.1:9222",
                "ws://127.0.0.1:9222/devtools/browser/test",
            ),
            connection=connection,
            interaction=Mock(),
        )
        backend._owns_browser = True
        backend.open()

        backend.close()

        connection.command.assert_called_with("Browser.close")
        cdp_page.return_value.close.assert_not_called()


class FakeCdpPage:
    def __init__(self) -> None:
        self.commands: list[tuple[str, dict[str, object]]] = []
        self.wait_count = 0

    def evaluate(self, expression: str) -> object:
        if expression == "location.href":
            return "https://www.bing.com/"
        return {"height": 1000, "viewport": 800, "width": 1200, "y": 0}

    def wait_for_value(self, expression: str, timeout_message: str) -> object:
        self.wait_count += 1
        if self.wait_count == 1:
            return {"x": 300, "y": 100}
        return "https://www.bing.com/search?q=test"

    def command(
        self,
        method: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.commands.append((method, params or {}))
        return {}


class CdpInteractionTests(unittest.TestCase):
    def test_implementation_inherits_interface(self) -> None:
        self.assertTrue(issubclass(CdpInteraction, Interaction))

    def test_search_uses_cdp_input_commands(self) -> None:
        page = FakeCdpPage()
        interaction = CdpInteraction(
            page,
            SearchConfig(),
            sleeper=lambda _: None,
        )

        interaction.search("测试")

        methods = [method for method, _params in page.commands]
        inserted_text = [
            params["text"]
            for method, params in page.commands
            if method == "Input.insertText"
        ]
        self.assertIn("Input.dispatchMouseEvent", methods)
        self.assertIn("Input.dispatchKeyEvent", methods)
        self.assertEqual(inserted_text, ["测", "试"])


if __name__ == "__main__":
    unittest.main()
