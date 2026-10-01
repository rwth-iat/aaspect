import unittest
from unittest.mock import patch

from aaspect.main import hello, main


class TestHello(unittest.TestCase):
    def test_hello_default(self) -> None:
        self.assertEqual(hello(), "Hello, world!")

    def test_hello_with_name(self) -> None:
        self.assertEqual(hello("Python"), "Hello, Python!")

    @patch("builtins.print")
    def test_main_prints_hello_world(self, mock_print) -> None:
        main()
        mock_print.assert_called_once_with("Hello, world!")


if __name__ == "__main__":
    unittest.main()
