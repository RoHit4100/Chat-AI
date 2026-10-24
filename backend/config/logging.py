import json
import logging
import traceback
from datetime import datetime, timezone

class StructuredJsonFormatter(logging.Formatter):
    """Format log records as structured single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include structured request/context attributes if present on record
        for attr in ("request_id", "user_id", "thread_id", "path", "method", "status_code", "duration_ms", "client_ip"):
            val = getattr(record, attr, None)
            if val is not None:
                log_obj[attr] = val

        # Include traceback details if an exception occurred
        if record.exc_info:
            log_obj["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "stack": self.formatException(record.exc_info),
            }

        return json.dumps(log_obj, ensure_ascii=False)
