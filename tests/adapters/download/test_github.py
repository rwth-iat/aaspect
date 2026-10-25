import hashlib
import time
import unittest
from unittest import mock

from aaspect.adapters.download import github
from aaspect.adapters.download.github import GithubDownload
from aaspect.domain.pinned import PinnedFile

_CONTENT = b"<schema/>"
_PINNED = PinnedFile(
    "owner/repo",
    "a" * 40,
    "schemas/xml/A file.xsd",
    len(_CONTENT),
    hashlib.sha256(_CONTENT).hexdigest(),
)


class TestGithubDownload(unittest.TestCase):
    def test_reads_the_pinned_path_and_checks_it(self) -> None:
        with mock.patch.object(GithubDownload, "_read", return_value=_CONTENT) as read:
            self.assertEqual(GithubDownload("https://mirror/")(_PINNED), _CONTENT)
        read.assert_called_once_with(
            f"https://mirror/owner/repo/{'a' * 40}/schemas/xml/A%20file.xsd", len(_CONTENT)
        )

    def test_refuses_other_content(self) -> None:
        for content in (b"<schemX/>", _CONTENT + b" "):
            with (
                self.subTest(content=content),
                mock.patch.object(GithubDownload, "_read", return_value=content),
                self.assertRaises(ValueError),
            ):
                GithubDownload()(_PINNED)

    def test_a_server_sending_byte_by_byte_meets_the_deadline(self) -> None:
        class Dripping:
            def __enter__(self) -> "Dripping":
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read1(self, size: int) -> bytes:
                time.sleep(0.01)
                return b"x"

        with (
            mock.patch.object(github._OPENER, "open", return_value=Dripping()),
            self.assertRaises(TimeoutError),
        ):
            GithubDownload(seconds=0.1)._read("https://mirror/x", 10_000)

    def test_only_https_without_credentials(self) -> None:
        for url in (
            "http://mirror",
            "file:///etc",
            "ftp://mirror",
            "https://user:token@mirror",
            "https://mirror?token=1",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                GithubDownload(url)

    def test_opener_has_no_file_ftp_or_redirects(self) -> None:
        handlers = {type(handler).__name__ for handler in vars(github._OPENER)["handlers"]}
        self.assertFalse(handlers & {"FileHandler", "FTPHandler", "HTTPRedirectHandler"})
        self.assertIn("_NoRedirects", handlers)


if __name__ == "__main__":
    unittest.main()
