import logging
import re

# The key in a report URL is the report's only access control; logs are read by more
# people than reports are.
_REPORT_KEY = re.compile(r"(/reports/[A-Za-z0-9_-]{6})[A-Za-z0-9_-]+")


class MaskReportKeys(logging.Filter):
    """Shortens report keys in uvicorn's access log to their first six characters."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                _REPORT_KEY.sub(r"\1…", arg) if isinstance(arg, str) else arg for arg in record.args
            )
        return True
