"""Image provenance survives the same-origin HTTP gateway."""

import asyncio
import httpx
import pytest
from fastapi import HTTPException
import main


def test_frame_gateway_preserves_original_frame_metadata(monkeypatch):
    response = httpx.Response(
        200,
        content=b"image",
        headers={
            "Content-Type": "image/jpeg",
            "X-Frame-Number": "7",
            "X-Frame-Rendered-At": "2026-10-15T20:00:00Z",
            "X-Source-Tick": "4",
            "X-View-Mode": "replay",
            "X-View-Snapshot-Id": "12",
            "X-Renderer-Ready": "false",
            "Unrelated-Internal-Header": "omit",
        },
    )

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, method, url, **kwargs):
            assert method == "GET" and url == "http://127.0.0.1:8091/frame.jpg"
            return response

    class Request:
        method = "GET"

        async def body(self):
            return b""

    monkeypatch.setattr(main.httpx, "AsyncClient", Client)
    result = asyncio.run(main.render_proxy("frame.jpg", Request()))
    assert result.body == b"image"
    assert result.headers["x-frame-number"] == "7"
    assert result.headers["x-frame-rendered-at"] == "2026-10-15T20:00:00Z"
    assert result.headers["x-view-snapshot-id"] == "12"
    assert result.headers["x-renderer-ready"] == "false"
    assert "unrelated-internal-header" not in result.headers


def test_gateway_rejects_unexposed_native_routes():
    with pytest.raises(HTTPException) as error:
        asyncio.run(main.render_proxy("internal/arbitrary", None))
    assert error.value.status_code == 404
