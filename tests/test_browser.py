import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from auto_searcher.browsers import Browser, EdgeBrowser, SearchBrowser
from auto_searcher.browsers.cdp import EdgeEndpoint
from auto_searcher.schemas import BrowserConfig, SearchConfig
from selenium.webdriver.common.by import By


class BrowserTests(unittest.TestCase):
    def test_browser_inheritance(self) -> None:
        self.assertTrue(issubclass(SearchBrowser, Browser))
        self.assertTrue(issubclass(EdgeBrowser, SearchBrowser))

    def test_search_box_uses_semantic_name_locator(self) -> None:
        self.assertEqual(SearchBrowser.SEARCH_BOX_LOCATOR, (By.NAME, "q"))

    def test_required_selenium_resources_are_available(self) -> None:
        EdgeBrowser.validate_runtime()

    @patch("auto_searcher.browsers.edge_browser.CdpEdgeBrowser")
    @patch.object(EdgeBrowser, "_get_debugger_product", return_value=None)
    @patch(
        "auto_searcher.browsers.edge_browser.read_edge_endpoint",
        return_value=EdgeEndpoint(
            "127.0.0.1:9222",
            "ws://127.0.0.1:9222/devtools/browser/test",
        ),
    )
    def test_open_uses_cdp_when_only_websocket_discovery_is_available(
        self,
        _read_edge_endpoint,
        _get_debugger_product,
        cdp_edge_browser,
    ) -> None:
        config = BrowserConfig(
            user_data_dir="D:/EdgeProfile",
            auto_detect_debugger=True,
        )
        browser = EdgeBrowser(config, SearchConfig(), sleeper=lambda _: None)

        browser.open()
        browser.search("topic")
        browser.browse_results()
        browser.close()

        delegate = cdp_edge_browser.return_value
        delegate.open.assert_called_once_with()
        delegate.search.assert_called_once_with("topic")
        delegate.browse_results.assert_called_once_with()
        delegate.close.assert_called_once_with()

    @patch("auto_searcher.browsers.edge_browser.CdpConnection")
    @patch.object(EdgeBrowser, "_get_debugger_product", return_value=None)
    @patch(
        "auto_searcher.browsers.edge_browser.read_edge_endpoint",
        return_value=EdgeEndpoint(
            "127.0.0.1:9222",
            "ws://127.0.0.1:9222/devtools/browser/test",
        ),
    )
    def test_check_detects_edge_151_without_creating_a_tab(
        self,
        _read_edge_endpoint,
        _get_debugger_product,
        cdp_connection,
    ) -> None:
        cdp_connection.return_value.command.return_value = {
            "product": "Edg/151.0"
        }
        config = BrowserConfig(
            user_data_dir="D:/EdgeProfile",
            auto_detect_debugger=True,
        )

        endpoint = EdgeBrowser.detect_cdp_endpoint(config)

        self.assertEqual(endpoint.address, "127.0.0.1:9222")
        cdp_connection.return_value.command.assert_called_once_with(
            "Browser.getVersion"
        )

    @patch("auto_searcher.browsers.edge_browser.CdpEdgeBrowser")
    @patch("auto_searcher.browsers.edge_browser.subprocess.Popen")
    @patch.object(EdgeBrowser, "_edge_process_is_running", return_value=False)
    @patch(
        "auto_searcher.browsers.edge_browser.read_edge_major_version",
        return_value=151,
    )
    @patch(
        "auto_searcher.browsers.edge_browser.find_edge_executable",
        return_value=Path("C:/Program Files/Microsoft/Edge/msedge.exe"),
    )
    @patch(
        "auto_searcher.browsers.edge_browser.default_edge_user_data_dir",
        return_value=Path("D:/EdgeProfile"),
    )
    @patch(
        "auto_searcher.browsers.edge_browser.read_edge_endpoint",
        side_effect=[
            None,
            EdgeEndpoint(
                "127.0.0.1:9222",
                "ws://127.0.0.1:9222/devtools/browser/test",
            ),
        ],
    )
    def test_edge_151_launches_without_starting_an_edgedriver_session(
        self,
        _read_edge_endpoint,
        _default_user_data_dir,
        _find_edge_executable,
        _read_edge_major_version,
        _edge_process_is_running,
        popen,
        cdp_edge_browser,
    ) -> None:
        config = BrowserConfig(
            user_data_dir="D:/EdgeProfile",
            auto_detect_debugger=True,
        )
        browser = EdgeBrowser(config, SearchConfig(), sleeper=lambda _: None)

        browser.open()

        command = popen.call_args.args[0]
        self.assertNotIn("--remote-debugging-port=0", command)
        cdp_edge_browser.assert_called_once()
        self.assertTrue(cdp_edge_browser.call_args.kwargs["owns_browser"])

    @patch.object(
        EdgeBrowser,
        "_get_debugger_product",
        return_value="Edg/131",
    )
    @patch.object(
        EdgeBrowser,
        "_listening_edge_addresses",
        return_value=("127.0.0.1:9224",),
    )
    def test_debugger_detection_uses_live_edge_listener(
        self,
        _listening_addresses,
        get_debugger_product,
    ) -> None:
        address = EdgeBrowser.detect_debugger_address("D:/EdgeProfile")

        self.assertEqual(address, "127.0.0.1:9224")
        get_debugger_product.assert_called_once_with("127.0.0.1:9224")

    @patch.object(
        EdgeBrowser,
        "_get_debugger_product",
        side_effect=[None, "Edg/131"],
    )
    @patch.object(
        EdgeBrowser,
        "_listening_edge_addresses",
        return_value=("127.0.0.1:3761", "127.0.0.1:9224"),
    )
    def test_debugger_detection_uses_verified_edge_listener(
        self,
        _listening_addresses,
        get_debugger_product,
    ) -> None:
        address = EdgeBrowser.detect_debugger_address("D:/EdgeProfile")

        self.assertEqual(address, "127.0.0.1:9224")
        self.assertEqual(
            [call.args[0] for call in get_debugger_product.call_args_list],
            ["127.0.0.1:3761", "127.0.0.1:9224"],
        )

    @patch.object(EdgeBrowser, "_edge_process_ids", return_value={"24964"})
    @patch("auto_searcher.browsers.edge_browser.subprocess.run")
    def test_edge_listener_detection_uses_live_msedge_processes(
        self,
        run,
        _edge_process_ids,
    ) -> None:
        run.return_value = Mock(
            stdout=(
                "TCP 127.0.0.1:3761 0.0.0.0:0 LISTENING 24964\n"
                "TCP 127.0.0.1:5000 0.0.0.0:0 LISTENING 12345\n"
                "TCP 127.0.0.1:6000 127.0.0.1:443 ESTABLISHED 24964\n"
            )
        )

        self.assertEqual(
            EdgeBrowser._listening_edge_addresses(),
            ("127.0.0.1:3761",),
        )

    @patch("auto_searcher.browsers.edge_browser.EdgeWebDriver")
    @patch.object(EdgeBrowser, "_get_debugger_product", return_value="Edg/131")
    def test_open_attaches_when_debugger_address_is_configured(
        self,
        _get_debugger_product,
        edge_driver,
    ) -> None:
        config = BrowserConfig(debugger_address="127.0.0.1:9222")
        browser = EdgeBrowser(config, SearchConfig(), sleeper=lambda _: None)
        browser.open()

        options = edge_driver.call_args.kwargs["options"]
        self.assertEqual(
            options.experimental_options["debuggerAddress"],
            "127.0.0.1:9222",
        )
        self.assertFalse(browser._owns_driver)

    @patch("auto_searcher.browsers.edge_browser.EdgeWebDriver")
    @patch.object(
        EdgeBrowser,
        "detect_debugger_address",
        return_value="127.0.0.1:9384",
    )
    def test_open_attaches_to_automatically_detected_debugger(
        self,
        _detect_debugger,
        edge_driver,
    ) -> None:
        config = BrowserConfig(
            user_data_dir="D:/EdgeProfile",
            auto_detect_debugger=True,
        )
        browser = EdgeBrowser(config, SearchConfig(), sleeper=lambda _: None)
        browser.open()

        options = edge_driver.call_args.kwargs["options"]
        self.assertEqual(
            options.experimental_options["debuggerAddress"],
            "127.0.0.1:9384",
        )
        self.assertFalse(browser._owns_driver)

    @patch("auto_searcher.browsers.edge_browser.EdgeWebDriver")
    @patch.object(EdgeBrowser, "_get_debugger_product", return_value=None)
    def test_open_launches_new_edge_when_debugger_is_unavailable(
        self,
        _get_debugger_product,
        edge_driver,
    ) -> None:
        config = BrowserConfig(
            user_data_dir="D:/EdgeProfile",
            debugger_address="127.0.0.1:9222",
        )
        browser = EdgeBrowser(config, SearchConfig(), sleeper=lambda _: None)
        browser.open()

        self.assertEqual(edge_driver.call_count, 1)
        launch_options = edge_driver.call_args.kwargs["options"]
        self.assertIn("--user-data-dir=D:/EdgeProfile", launch_options.arguments)
        self.assertIn(
            "--remote-debugging-port=9222",
            launch_options.arguments,
        )
        self.assertIn("--log-level=3", launch_options.arguments)
        self.assertIn("--disable-logging", launch_options.arguments)
        self.assertIn(
            "--disable-blink-features=AutomationControlled",
            launch_options.arguments,
        )
        self.assertEqual(
            launch_options.experimental_options["excludeSwitches"],
            ["enable-automation", "enable-logging"],
        )
        self.assertFalse(
            launch_options.experimental_options["useAutomationExtension"]
        )
        edge_driver.return_value.execute_cdp_cmd.assert_any_call(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": SearchBrowser.WEBDRIVER_OVERRIDE_SCRIPT},
        )
        self.assertTrue(browser._owns_driver)

    @patch("auto_searcher.browsers.edge_browser.EdgeWebDriver")
    @patch.object(EdgeBrowser, "_automatic_debugger_port", return_value=9222)
    def test_open_uses_configured_profile_without_debugger_address(
        self,
        _automatic_debugger_port,
        edge_driver,
    ) -> None:
        config = BrowserConfig(
            user_data_dir="D:/EdgeProfile",
            profile_name="Profile 1",
            debugger_address=None,
        )
        browser = EdgeBrowser(config, SearchConfig(), sleeper=lambda _: None)
        browser.open()

        options = edge_driver.call_args.kwargs["options"]
        self.assertIn("--user-data-dir=D:/EdgeProfile", options.arguments)
        self.assertIn("--profile-directory=Profile 1", options.arguments)
        self.assertIn("--remote-debugging-port=9222", options.arguments)
        self.assertTrue(browser._owns_driver)

    @patch.object(EdgeBrowser, "_port_is_available", return_value=False)
    def test_automatic_debugger_port_falls_back_when_9222_is_occupied(
        self,
        _port_is_available,
    ) -> None:
        browser = EdgeBrowser(
            BrowserConfig(),
            SearchConfig(),
            sleeper=lambda _: None,
        )

        self.assertEqual(browser._automatic_debugger_port(), 0)

    @patch.object(EdgeBrowser, "_port_is_available", return_value=True)
    def test_automatic_debugger_port_prefers_9222_when_available(
        self,
        _port_is_available,
    ) -> None:
        browser = EdgeBrowser(
            BrowserConfig(),
            SearchConfig(),
            sleeper=lambda _: None,
        )

        self.assertEqual(browser._automatic_debugger_port(), 9222)

    @patch.object(EdgeBrowser, "_edge_process_is_running", return_value=True)
    @patch(
        "auto_searcher.browsers.edge_browser.default_edge_user_data_dir",
        return_value=Path("D:/EdgeUserData"),
    )
    def test_default_user_directory_fails_fast_when_edge_is_running(
        self,
        _default_edge_user_data_dir,
        _edge_process_is_running,
    ) -> None:
        config = BrowserConfig(user_data_dir="D:/EdgeUserData")
        browser = EdgeBrowser(config, SearchConfig(), sleeper=lambda _: None)

        with self.assertRaisesRegex(RuntimeError, "Profile 1"):
            browser._before_launch()


if __name__ == "__main__":
    unittest.main()
