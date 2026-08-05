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
        "auto_searcher.browsers.chromium_browser.read_active_endpoint",
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
        "auto_searcher.browsers.chromium_browser.read_http_endpoint",
        return_value=Endpoint(
            "127.0.0.1:9224",
            "ws://127.0.0.1:9224/devtools/browser/test",
        ),
    )
    @patch.object(
        EdgeBrowser,
        "_listening_addresses",
        return_value=("127.0.0.1:9224",),
    )
    @patch(
        "auto_searcher.browsers.chromium_browser.read_active_endpoint",
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
    @patch("auto_searcher.browsers.chromium_browser.subprocess.Popen")
    @patch.object(EdgeBrowser, "_process_is_running", return_value=False)
    @patch.object(
        EdgeBrowser,
        "_find_executable",
        return_value=Path("C:/Program Files/Microsoft/Edge/msedge.exe"),
    )
    @patch(
        "auto_searcher.browsers.chromium_browser.read_active_endpoint",
        return_value=Endpoint(
            "127.0.0.1:9222",
            "ws://127.0.0.1:9222/devtools/browser/test",
        ),
    )
    def test_launch_passes_no_browser_arguments(
        self,
        _read_file_endpoint,
        _find_executable,
        _edge_running,
        popen,
        _is_supported_endpoint,
    ) -> None:
        browser = EdgeBrowser(
            BrowserConfig(
                user_data_dir="D:/EdgeProfile",
                profile_name="Profile 1",
                debugger_address="127.0.0.1:9222",
            ),
            SearchConfig(),
            sleeper=lambda _: None,
        )

        endpoint = browser._launch()

        self.assertEqual(endpoint.address, "127.0.0.1:9222")
        self.assertEqual(
            popen.call_args.args[0],
            [str(Path("C:/Program Files/Microsoft/Edge/msedge.exe"))],
        )
        _read_file_endpoint.assert_called_once_with("D:/EdgeProfile")

if __name__ == "__main__":
    unittest.main()
