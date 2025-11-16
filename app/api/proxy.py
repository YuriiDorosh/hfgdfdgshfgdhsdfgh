import time
import asyncio
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.models.proxy_log import ProxyLog

router = APIRouter(prefix="/proxy", tags=["proxy"])

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def _safe_bytes_to_str(data: bytes | None, limit: int = 5000) -> str:
    """Safe body to string conversion with length limit."""
    if not data:
        return ""
    try:
        s = data.decode("utf-8")
    except UnicodeDecodeError:
        s = data.decode("utf-8", errors="ignore")
    if len(s) > limit:
        return s[:limit] + f"... (truncated, total {len(s)} chars)"
    return s


async def _save_proxy_log(
    db: AsyncSession,
    *,
    client_ip: Optional[str],
    method: str,
    path: str,
    upstream_url: str,
    query_params: Dict[str, Any],
    request_headers: Dict[str, Any],
    request_body: str,
    response_status: Optional[int],
    response_headers: Optional[Dict[str, Any]],
    response_body: Optional[str],
    duration_ms: Optional[float],
    error: Optional[str],
) -> None:
    log = ProxyLog(
        client_ip=client_ip,
        method=method,
        path=path,
        upstream_url=upstream_url,
        query_params=query_params or None,
        request_headers=request_headers or None,
        request_body=request_body or None,
        response_status=response_status,
        response_headers=response_headers or None,
        response_body=response_body or None,
        duration_ms=duration_ms,
        error=error,
    )

    try:
        db.add(log)
        await db.commit()
    except Exception:
        await db.rollback()


@router.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_request(
    full_path: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    base = settings.UPSTREAM_BASE_URL.rstrip("/")
    full_path_clean = full_path.lstrip("/")
    target_url = f"{base}/{full_path_clean}" if full_path_clean else base

    query_params = dict(request.query_params)
    body_bytes = await request.body()

    incoming_headers = dict(request.headers)
    for h in list(incoming_headers.keys()):
        if h.lower() in HOP_BY_HOP_HEADERS:
            incoming_headers.pop(h, None)

    client_ip = request.client.host if request.client else None
    method = request.method
    path = request.url.path

    max_retries = settings.PROXY_MAX_RETRIES
    delay = settings.PROXY_RETRY_DELAY_SECONDS

    start_ts = time.monotonic()
    attempts = 0
    upstream_response: Optional[httpx.Response] = None
    last_exc: Optional[Exception] = None

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for attempt in range(1, max_retries + 1):
            attempts = attempt
            try:
                upstream_response = await client.request(
                    method=method,
                    url=target_url,
                    params=query_params,
                    content=body_bytes,
                    headers=incoming_headers,
                )
                # any HTTP response counts as successful attempt
                break
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < max_retries:
                    await asyncio.sleep(delay)
                else:
                    pass

    duration_ms = (time.monotonic() - start_ts) * 1000.0

    if upstream_response is None:
        error_msg = (
            f"{type(last_exc).__name__ if last_exc else 'UnknownError'}: "
            f"{str(last_exc) if last_exc else 'No response from upstream'}; "
            f"attempts={attempts}, delay={delay}s"
        )

        await _save_proxy_log(
            db,
            client_ip=client_ip,
            method=method,
            path=path,
            upstream_url=target_url,
            query_params=query_params,
            request_headers=incoming_headers,
            request_body=_safe_bytes_to_str(body_bytes),
            response_status=None,
            response_headers=None,
            response_body=None,
            duration_ms=duration_ms,
            error=error_msg,
        )

        raise HTTPException(
            status_code=502,
            detail=f"Upstream unreachable after {attempts} attempts",
        )

    response_headers = dict(upstream_response.headers)
    for h in list(response_headers.keys()):
        if h.lower() in HOP_BY_HOP_HEADERS:
            response_headers.pop(h, None)

    response_body_str = _safe_bytes_to_str(upstream_response.content)

    await _save_proxy_log(
        db,
        client_ip=client_ip,
        method=method,
        path=path,
        upstream_url=target_url,
        query_params=query_params,
        request_headers=incoming_headers,
        request_body=_safe_bytes_to_str(body_bytes),
        response_status=upstream_response.status_code,
        response_headers=response_headers,
        response_body=response_body_str,
        duration_ms=duration_ms,
        error=f"attempts={attempts}, delay={delay}s",
    )

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
    )
