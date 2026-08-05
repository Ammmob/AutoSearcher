import unittest

from auto_searcher.__main__ import _parser


class CliTests(unittest.TestCase):
    def test_run_is_default_command(self) -> None:
        self.assertEqual(_parser().parse_args([]).command, "run")

    def test_explicit_command_is_preserved(self) -> None:
        self.assertEqual(_parser().parse_args(["check"]).command, "check")

    def test_help_documents_the_default_command(self) -> None:
        help_text = _parser().format_help()

        self.assertIn("[{run,check,topics}]", help_text)
        self.assertIn("默认: run", help_text)


if __name__ == "__main__":
    unittest.main()
