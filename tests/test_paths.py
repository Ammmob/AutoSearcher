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

        self.assertIsNone(config.browser.user_data_dir)
        self.assertIsNone(config.browser.profile_name)

    def test_configured_user_directory_does_not_infer_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            user_data_dir = temp_path / "User Data"
            config_path = temp_path / "config.yaml"
            config_path.write_text(
                "browser:\n"
                f"  user_data_dir: {user_data_dir.as_posix()}\n"
                "search: {}\n"
                "sources: {}\n",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.browser.user_data_dir, str(user_data_dir.resolve()))
        self.assertIsNone(config.browser.profile_name)

    def test_configured_edge_profile_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            user_data_dir = temp_path / "User Data"
            config_path = temp_path / "config.yaml"
            config_path.write_text(
                "browser:\n"
                f"  user_data_dir: {user_data_dir.as_posix()}\n"
                "  profile_name: Default\n"
                "search: {}\n"
                "sources: {}\n",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.browser.profile_name, "Default")

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

    def test_profile_named_auto_is_treated_as_an_explicit_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "config.yaml"
            config_path.write_text(
                "browser:\n"
                "  profile_name: auto\n"
                "search: {}\n"
                "sources: {}\n",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.browser.profile_name, "auto")

    def test_default_config_is_project_config_when_running_from_source(self) -> None:
        self.assertEqual(
            default_config_path(),
            application_dir() / "config" / "config.yaml",
        )


if __name__ == "__main__":
    unittest.main()
