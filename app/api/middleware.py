"""HTTP middleware: request ids, request body size limit and one access-log line per request."""
import logging
import re
import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

import config
from app.api.logging_setup import request_id_var

log = logging.getLogger("app.access")
REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")  # client ids are echoed, so keep them tame


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, rejects oversized bodies early and logs method/path/status/time."""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > config.REQUEST_MAX_BYTES:
                response = JSONResponse({"detail": "Request body too large"}, status_code=413)
            else:
                response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            log.info("request", extra={
                "method": request.method, "path": request.url.path, "status_code": response.status_code,
                "duration_ms": int((time.perf_counter() - start) * 1000),
            })
            return response
        finally:
            request_id_var.reset(token)
