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
    @patch.object(
        EdgeBrowser,
        "_default_user_data_dir",
        return_value=Path("D:/DefaultEdgeData"),
    )
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
        _default_user_data_dir,
        is_supported_endpoint,
    ) -> None:
        config = BrowserConfig(
            auto_detect_debugger=True,
        )

        endpoint = EdgeBrowser.detect_endpoint(config)

        self.assertEqual(endpoint.address, "127.0.0.1:9222")
        _read_endpoint.assert_called_once_with(Path("D:/DefaultEdgeData"), None)
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
    def test_launch_only_passes_explicit_user_arguments(
        self,
        _read_file_endpoint,
        _find_executable,
        _edge_running,
        popen,
        _is_supported_endpoint,
    ) -> None:
        browser = EdgeBrowser(
            BrowserConfig(
                debugger_address="127.0.0.1:9222",
            ),
            SearchConfig(),
            sleeper=lambda _: None,
        )

        implicit_endpoint = browser._launch()

        self.assertEqual(implicit_endpoint.address, "127.0.0.1:9222")
        self.assertEqual(
            popen.call_args.args[0],
            [
                str(Path("C:/Program Files/Microsoft/Edge/msedge.exe")),
                "--remote-debugging-port=9222",
            ],
        )

        explicit_browser = EdgeBrowser(
            BrowserConfig(
                user_data_dir="D:/EdgeProfile",
                profile_name="Profile 1",
            ),
            SearchConfig(),
            sleeper=lambda _: None,
        )

        explicit_endpoint = explicit_browser._launch()

        self.assertEqual(explicit_endpoint.address, "127.0.0.1:9222")
        self.assertEqual(
            popen.call_args.args[0],
            [
                str(Path("C:/Program Files/Microsoft/Edge/msedge.exe")),
                "--profile-directory=Profile 1",
                "--user-data-dir=D:/EdgeProfile",
            ],
        )
        self.assertEqual(_read_file_endpoint.call_count, 2)

    def test_edge_launch_command_omits_all_unconfigured_arguments(self) -> None:
        browser = EdgeBrowser(BrowserConfig(), SearchConfig())
        executable = Path("C:/Program Files/Microsoft/Edge/msedge.exe")

        command, expected_address = browser._launch_command(executable)

        self.assertEqual(command, [str(executable)])
        self.assertIsNone(expected_address)

if __name__ == "__main__":
    unittest.main()
