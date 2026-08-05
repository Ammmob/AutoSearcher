import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from auto_searcher.browsers import Browser, ChromiumBrowser, EdgeBrowser
from auto_searcher.browsers.cdp import CdpSession, Endpoint
from auto_searcher.schemas import BrowserConfig, SearchConfig


class BrowserTests(unittest.TestCase):
    def test_edge_browser_inherits_browser_and_holds_cdp_session(self) -> None:
        session = Mock(spec=CdpSession)
        browser = EdgeBrowser(
            BrowserConfig(),
            SearchConfig(),
            session=session,
        )

        browser.open()
        browser.search("topic")
        browser.browse_results()
        browser.close()

        self.assertIsInstance(browser, Browser)
        self.assertIsInstance(browser, ChromiumBrowser)
        self.assertEqual(browser.name, "Edge")
        session.open.assert_called_once_with()
        session.search.assert_called_once_with("topic")
        session.browse_results.assert_called_once_with()
        session.close.assert_called_once_with()


class EdgeBrowserTests(unittest.TestCase):
    @patch.object(EdgeBrowser, "_is_supported_endpoint", return_value=True)
    @patch(
        "auto_searcher.browsers.browser.read_active_endpoint",
        return_value=Endpoint(
            "127.0.0.1:9222",
            "ws://127.0.0.1:9222/devtools/browser/test",
        ),
    )
    def test_detects_endpoint_from_active_port_file(
        self,
        _read_endpoint,
        is_supported_endpoint,
    ) -> None:
        config = BrowserConfig(
            user_data_dir="D:/EdgeProfile",
            auto_detect_debugger=True,
        )

        endpoint = EdgeBrowser.detect_endpoint(config)

        self.assertEqual(endpoint.address, "127.0.0.1:9222")
        is_supported_endpoint.assert_called_once()

    @patch.object(EdgeBrowser, "_is_supported_endpoint", return_value=True)
    @patch(
        "auto_searcher.browsers.browser.read_http_endpoint",
        return_value=Endpoint(
            "127.0.0.1:9224",
            "ws://127.0.0.1:9224/devtools/browser/test",
        ),
    )
    @patch(
        "auto_searcher.browsers.edge_browser.listening_edge_addresses",
        return_value=("127.0.0.1:9224",),
    )
    @patch(
        "auto_searcher.browsers.browser.read_active_endpoint",
        return_value=None,
    )
    def test_classic_edge_can_be_detected_through_http_endpoint(
        self,
        _read_file_endpoint,
        _listening_addresses,
        _read_http_endpoint,
        _is_supported_endpoint,
    ) -> None:
        config = BrowserConfig(
            user_data_dir="D:/EdgeProfile",
            auto_detect_debugger=True,
        )

        endpoint = EdgeBrowser.detect_endpoint(config)

        self.assertEqual(endpoint.address, "127.0.0.1:9224")

    @patch.object(EdgeBrowser, "_is_supported_endpoint", return_value=True)
    @patch("auto_searcher.browsers.browser.subprocess.Popen")
    @patch(
        "auto_searcher.browsers.edge_browser.edge_process_is_running",
        return_value=False,
    )
    @patch("auto_searcher.browsers.browser.port_is_available", return_value=True)
    @patch(
        "auto_searcher.browsers.edge_browser.find_edge_executable",
        return_value=Path("C:/Program Files/Microsoft/Edge/msedge.exe"),
    )
    @patch(
        "auto_searcher.browsers.browser.read_active_endpoint",
        return_value=None,
    )
    @patch(
        "auto_searcher.browsers.browser.read_http_endpoint",
        return_value=Endpoint(
            "127.0.0.1:9222",
            "ws://127.0.0.1:9222/devtools/browser/test",
        ),
    )
    def test_launch_uses_same_9222_command_for_all_edge_versions(
        self,
        _read_http_endpoint,
        _read_file_endpoint,
        _find_executable,
        _port_available,
        _edge_running,
        popen,
        _is_supported_endpoint,
    ) -> None:
        browser = EdgeBrowser(
            BrowserConfig(user_data_dir="D:/EdgeProfile"),
            SearchConfig(),
            sleeper=lambda _: None,
        )

        endpoint = browser._launch()

        self.assertEqual(endpoint.address, "127.0.0.1:9222")
        command = popen.call_args.args[0]
        self.assertIn("--user-data-dir=D:/EdgeProfile", command)
        self.assertIn("--remote-debugging-port=9222", command)

    @patch("auto_searcher.browsers.browser.port_is_available", return_value=False)
    @patch(
        "auto_searcher.browsers.edge_browser.edge_process_is_running",
        return_value=False,
    )
    @patch(
        "auto_searcher.browsers.edge_browser.find_edge_executable",
        return_value=Path("C:/Program Files/Microsoft/Edge/msedge.exe"),
    )
    @patch("auto_searcher.browsers.browser.subprocess.Popen")
    @patch(
        "auto_searcher.browsers.browser.read_active_endpoint",
        side_effect=RuntimeError("stop after launch"),
    )
    def test_launch_uses_random_port_only_when_9222_is_occupied(
        self,
        _read_endpoint,
        popen,
        _find_executable,
        _edge_running,
        _port_available,
    ) -> None:
        browser = EdgeBrowser(BrowserConfig(), SearchConfig())

        with self.assertRaisesRegex(RuntimeError, "stop after launch"):
            browser._launch()

        self.assertIn("--remote-debugging-port=0", popen.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
