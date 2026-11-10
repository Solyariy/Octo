import time

from fastapi import Request, Response

from src.utils.logs import Logger
from src.utils.order import get_log_id


async def trace_requests(request: Request, call_next) -> Response:
    """Bind one `log_id` to the request, log its span, and echo it as `X-Request-ID`.

    Everything downstream (routes, background tasks, `asyncio.to_thread` work) runs in a
    copy of this context, so all of its log lines carry the same `log_id`.
    """
    started = time.perf_counter()
    Logger.info(
        "Request started",
        method=request.method,
        path=request.url.path,
    )
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
        response.headers["X-Request-ID"] = get_log_id()
        Logger.info(
            "Request finished",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        return response
