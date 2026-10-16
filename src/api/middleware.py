import time

from fastapi import Request, Response

from src.settings import LOG_ID
from src.utils.logs import Logger
from src.utils.order import get_uuid_str

REQUEST_ID_HEADER = "X-Request-ID"


async def trace_requests(request: Request, call_next) -> Response:
    """Bind one `log_id` to the request, log its span, and echo it as `X-Request-ID`.

    Everything downstream (routes, background tasks, `asyncio.to_thread` work) runs in a
    copy of this context, so all of its log lines carry the same `log_id`.
    """
    log_id = request.headers.get(REQUEST_ID_HEADER) or get_uuid_str()
    token = LOG_ID.set(log_id)
    started = time.perf_counter()
    Logger.info("Request started", method=request.method, path=request.url.path)
    try:
        response = await call_next(request)
    except Exception as e:
        Logger.error(
            "Request failed",
            error=e,
            method=request.method,
            path=request.url.path,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        raise
    else:
        response.headers[REQUEST_ID_HEADER] = log_id
        Logger.info(
            "Request finished",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        return response
    finally:
        LOG_ID.reset(token)
