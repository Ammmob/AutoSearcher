import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from auto_searcher.utils.config_utils import ConfigError, load_config
from auto_searcher.utils.path_utils import (
    application_dir,
    default_config_path,
    default_edge_user_data_dir,
    default_topic_cache_dir,
    resolve_configured_path,
)


class PathTests(unittest.TestCase):
    def test_edge_user_data_dir_uses_local_app_data(self) -> None:
        local_app_data = Path("D:/Users/tester/AppData/Local")
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
            resolved = default_edge_user_data_dir()

        expected = local_app_data / "Microsoft" / "Edge" / "User Data"
        self.assertEqual(resolved, expected.resolve())

    def test_configured_path_expands_environment_variables(self) -> None:
        base_dir = Path("D:/AutoSearcher/config")
        with patch.dict(os.environ, {"AUTOS_TEST_ROOT": "D:/PortableData"}):
            resolved = resolve_configured_path(
                "%AUTOS_TEST_ROOT%/Edge",
                base_dir,
            )

        self.assertEqual(resolved, Path("D:/PortableData/Edge").resolve())

    def test_topic_cache_uses_current_users_local_app_data(self) -> None:
        local_app_data = Path("D:/Users/tester/AppData/Local")
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
            resolved = default_topic_cache_dir()

        expected = local_app_data / "AutoSearcher" / "cache" / "sources"
        self.assertEqual(resolved, expected.resolve())

    def test_project_config_leaves_optional_edge_arguments_unset(self) -> None:
        local_app_data = Path("D:/Users/another-user/AppData/Local")
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
            config = load_config(application_dir() / "config" / "config.yaml")

        self.assertEqual(config.browser.args, ())

    def test_browser_arguments_expand_environment_variables(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "config.yaml"
            with patch.dict(os.environ, {"AUTOS_EDGE_DATA": "D:/Edge Data"}):
                config_path.write_text(
                    "browser:\n"
                    '  args: [\"--user-data-dir=%AUTOS_EDGE_DATA%\"]\n'
                    "search: {}\n"
                    "sources: {}\n",
                    encoding="utf-8",
                )

                config = load_config(config_path)

        self.assertEqual(config.browser.args, ("--user-data-dir=D:/Edge Data",))

    def test_browser_arguments_preserve_valued_and_flag_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(
                "browser:\n"
                "  args:\n"
                '    - "--profile-directory=Profile 1"\n'
                '    - "--flag-switches-begin"\n'
                '    - "--flag-switches-end"\n'
                "search: {}\n"
                "sources: {}\n",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(
            config.browser.args,
            (
                "--profile-directory=Profile 1",
                "--flag-switches-begin",
                "--flag-switches-end",
            ),
        )

    def test_config_rejects_non_finite_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(
                "browser:\n"
                "  page_timeout_seconds: .inf\n"
                "search: {}\n"
                "sources: {}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "有限数字"):
                load_config(config_path)

    def test_config_rejects_non_finite_range(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(
                "browser: {}\n"
                "search:\n"
                "  interval_seconds: [1, .nan]\n"
                "sources: {}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "有限数字"):
                load_config(config_path)

    def test_browser_arguments_reject_remote_debugging_port(self) -> None:
        for argument in ("--remote-debugging-port", "--REMOTE-DEBUGGING-PORT=9333"):
            with self.subTest(argument=argument), tempfile.TemporaryDirectory() as temp_dir:
                config_path = Path(temp_dir) / "config.yaml"
                config_path.write_text(
                    "browser:\n"
                    f'  args: ["{argument}"]\n'
                    "search: {}\n"
                    "sources: {}\n",
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(ConfigError, "由程序自动管理"):
                    load_config(config_path)

    def test_default_config_is_project_config_when_running_from_source(self) -> None:
        self.assertEqual(
            default_config_path(),
            application_dir() / "config" / "config.yaml",
        )


if __name__ == "__main__":
    unittest.main()
