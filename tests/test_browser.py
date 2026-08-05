import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
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
        config = BrowserConfig()

        endpoint = EdgeBrowser.detect_endpoint(config)

        self.assertEqual(endpoint.address, "127.0.0.1:9222")
        _read_endpoint.assert_called_once_with(Path("D:/DefaultEdgeData"))
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
            args=("--user-data-dir=D:/EdgeProfile",),
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
    @patch.object(EdgeBrowser, "_browser_manages_remote_debugging", return_value=False)
    def test_legacy_launch_uses_default_and_configured_debugging_ports(
        self,
        _managed_debugging,
        _read_file_endpoint,
        _find_executable,
        _edge_running,
        popen,
        _is_supported_endpoint,
    ) -> None:
        browser = EdgeBrowser(
            BrowserConfig(),
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
                args=(
                    "--profile-directory=Profile 1",
                    "--user-data-dir=D:/EdgeProfile",
                    "--remote-debugging-port",
                    "9224",
                ),
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
                "--remote-debugging-port=9224",
            ],
        )
        self.assertEqual(_read_file_endpoint.call_count, 2)

    @patch.object(EdgeBrowser, "_browser_manages_remote_debugging", return_value=True)
    def test_modern_edge_launch_omits_debugging_port(self, _managed_debugging) -> None:
        browser = EdgeBrowser(
            BrowserConfig(
                args=("--profile-directory=Profile 1", "--remote-debugging-port=9333")
            ),
            SearchConfig(),
        )
        executable = Path("C:/Program Files/Microsoft/Edge/msedge.exe")

        with self.assertLogs("auto_searcher.browsers.edge_browser", "WARNING"):
            command, expected_address = browser._launch_command(executable)

        self.assertEqual(
            command,
            [str(executable), "--profile-directory=Profile 1"],
        )
        self.assertIsNone(expected_address)

    def test_detects_browser_managed_debugging_from_local_state(self) -> None:
        with TemporaryDirectory() as directory:
            user_data_dir = Path(directory)
            (user_data_dir / "Local State").write_text(
                '{"devtools":{"remote_debugging":{"user-enabled":true}}}',
                encoding="utf-8",
            )
            browser = EdgeBrowser(
                BrowserConfig(args=(f"--user-data-dir={user_data_dir}",)),
                SearchConfig(),
            )

            self.assertTrue(browser._browser_manages_remote_debugging())

if __name__ == "__main__":
    unittest.main()
