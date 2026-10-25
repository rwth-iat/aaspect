import logging
import unittest

from aaspect.adapters.web.access_log import MaskReportKeys


class TestMaskReportKeys(unittest.TestCase):
    def test_report_keys_are_shortened(self) -> None:
        key = "Cp9GeMtorR_x-1234567890abcdefghijkl"
        record = logging.LogRecord(
            "uvicorn.access",
            logging.INFO,
            "",
            0,
            '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1:5", "GET", f"/reports/{key}/status", "1.1", 200),
            None,
        )

        MaskReportKeys().filter(record)

        self.assertNotIn(key, record.getMessage())
        self.assertIn("/reports/Cp9GeM…/status", record.getMessage())


if __name__ == "__main__":
    unittest.main()
