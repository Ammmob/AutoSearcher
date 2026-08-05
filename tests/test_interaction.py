import unittest
from unittest.mock import MagicMock, patch

from selenium.webdriver.common.keys import Keys

from auto_searcher.browsers import SearchInteraction
from auto_searcher.schemas import SearchConfig


class SearchInteractionTests(unittest.TestCase):
    @patch("auto_searcher.browsers.search_interaction.ActionChains")
    @patch("auto_searcher.browsers.search_interaction.WebDriverWait")
    def test_search_uses_pointer_and_keyboard_actions(
        self,
        wait_type,
        action_chains_type,
    ) -> None:
        driver = MagicMock()
        driver.current_url = "https://example.com"
        search_box = MagicMock()
        wait_type.return_value.until.side_effect = [search_box, True]
        actions = action_chains_type.return_value
        for method_name in (
            "move_to_element",
            "pause",
            "click",
            "key_down",
            "key_up",
            "send_keys",
        ):
            getattr(actions, method_name).return_value = actions

        interaction = SearchInteraction(
            SearchConfig(),
            page_timeout_seconds=10,
            sleeper=lambda _: None,
        )
        interaction.search(driver, "AI news")

        actions.move_to_element.assert_called_once_with(search_box)
        actions.click.assert_called_once_with()
        actions.key_down.assert_called_once_with(Keys.CONTROL)
        actions.key_up.assert_called_once_with(Keys.CONTROL)
        actions.send_keys.assert_any_call("A")
        actions.send_keys.assert_any_call(Keys.ENTER)

    @patch("auto_searcher.browsers.search_interaction.ActionChains")
    def test_browse_results_uses_wheel_actions(self, action_chains_type) -> None:
        driver = MagicMock()
        driver.execute_script.side_effect = [
            {"height": 1800, "viewport": 800, "y": 0},
            {"height": 1800, "viewport": 800, "y": 0},
            {"height": 1800, "viewport": 800, "y": 400},
        ]
        rng = MagicMock()
        rng.randint.side_effect = [2, 400, 400]
        rng.uniform.return_value = 1.0
        rng.random.return_value = 1.0
        actions = action_chains_type.return_value
        actions.scroll_by_amount.return_value = actions

        interaction = SearchInteraction(
            SearchConfig(),
            page_timeout_seconds=10,
            rng=rng,
            sleeper=lambda _: None,
        )
        interaction.browse_results(driver)

        self.assertEqual(actions.scroll_by_amount.call_count, 2)
        actions.scroll_by_amount.assert_any_call(0, 400)
        self.assertEqual(actions.perform.call_count, 2)

    def test_page_height_increases_dwell_time(self) -> None:
        short_page = MagicMock()
        short_page.execute_script.return_value = {
            "height": 800,
            "viewport": 800,
            "y": 0,
        }
        long_page = MagicMock()
        long_page.execute_script.return_value = {
            "height": 3800,
            "viewport": 800,
            "y": 0,
        }
        rng = MagicMock()
        rng.uniform.return_value = 2.0
        interaction = SearchInteraction(
            SearchConfig(),
            page_timeout_seconds=10,
            rng=rng,
            sleeper=lambda _: None,
        )

        short_dwell = interaction._page_dwell_seconds(short_page, (2.0, 3.0))
        long_dwell = interaction._page_dwell_seconds(long_page, (2.0, 3.0))

        self.assertGreater(long_dwell, short_dwell)


if __name__ == "__main__":
    unittest.main()
