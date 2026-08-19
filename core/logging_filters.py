import logging
import re

_TOKEN_PATTERN = re.compile(r"(Bearer\s+)[A-Za-z0-9\-_\.=]+", re.IGNORECASE)


class RedactTokenFilter(logging.Filter):
    """
    Belt-and-braces filter: even though we deliberately avoid logging
    cluster tokens anywhere in application code, this makes sure that if a
    library we depend on (e.g. an HTTP client) ever logs an Authorization
    header, the token portion never reaches log output/log aggregation.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _TOKEN_PATTERN.sub(r"\1[REDACTED]", record.msg)
        return True
