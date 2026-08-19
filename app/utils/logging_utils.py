"""
Utilidades de logging estructurado (JSON) con correlación por request.
"""
import json
import logging
from datetime import datetime, timezone

from flask import g, has_request_context, request

_RESERVED_LOG_RECORD_ATTRS = set(logging.LogRecord(
    name='', level=0, pathname='', lineno=0, msg='', args=(), exc_info=None
).__dict__.keys()) | {'message', 'asctime'}


class RequestIdFilter(logging.Filter):
    """Adjunta el request_id actual (si existe) a cada registro de log."""

    def filter(self, record):
        record.request_id = getattr(g, 'request_id', None) if has_request_context() else None
        return True


class JsonFormatter(logging.Formatter):
    """Formatea cada log como una línea JSON, ideal para Render/plataformas de logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'timestamp': datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'message': record.getMessage(),
        }

        request_id = getattr(record, 'request_id', None)
        if request_id:
            payload['request_id'] = request_id

        if has_request_context():
            payload['method'] = request.method
            payload['path'] = request.path

        # Incluir campos extra pasados vía logger.info(..., extra={...})
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_ATTRS and key not in payload and key != 'request_id':
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = str(value)

        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)
