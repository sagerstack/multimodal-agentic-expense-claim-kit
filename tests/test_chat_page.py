"""Smoke tests verifying chat page renders with expected SSE/HTMX/Alpine attributes."""

from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def chatApp():
    """Create a test FastAPI app with session middleware and all routers."""
    from fastapi import FastAPI
    from starlette.middleware.sessions import SessionMiddleware
    from starlette.staticfiles import StaticFiles

    from agentic_claims.web.main import projectRoot
    from agentic_claims.web.routers.chat import router as chatRouter
    from agentic_claims.web.routers.pages import router as pagesRouter

    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="test-secret",
        session_cookie="test_session",
    )
    app.mount("/static", StaticFiles(directory=str(projectRoot / "static")), name="static")
    app.include_router(chatRouter)
    app.include_router(pagesRouter)
    app.state.graph = MagicMock()
    return app


@pytest.mark.asyncio
async def testChatPageRendersWithSseConnect(chatApp):
    transport = ASGITransport(app=chatApp)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert 'sse-connect="/chat/stream"' in response.text


@pytest.mark.asyncio
async def testChatPageRendersWithChatForm(chatApp):
    transport = ASGITransport(app=chatApp)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
    assert 'hx-post="/chat/message"' in response.text
    assert "multipart/form-data" in response.text


@pytest.mark.asyncio
async def testChatPageRendersWithResetButton(chatApp):
    transport = ASGITransport(app=chatApp)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
    assert 'hx-post="/chat/reset"' in response.text


@pytest.mark.asyncio
async def testChatPageRendersWithAlpineState(chatApp):
    transport = ASGITransport(app=chatApp)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
    assert "x-data" in response.text


@pytest.mark.asyncio
async def testChatPageRendersWithSseSwapTargets(chatApp):
    transport = ASGITransport(app=chatApp)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
    assert 'sse-swap="token"' in response.text
    assert 'sse-swap="message"' in response.text
    assert 'sse-swap="thinking-done"' in response.text
    assert 'sse-swap="done"' in response.text


@pytest.mark.asyncio
async def testChatPageRendersWithThinkingPanel(chatApp):
    transport = ASGITransport(app=chatApp)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
    assert "thinkingPanel" in response.text


@pytest.mark.asyncio
async def testChatPageRendersWithFileInput(chatApp):
    transport = ASGITransport(app=chatApp)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
    assert 'name="receipt"' in response.text
    assert 'accept="image/*"' in response.text


@pytest.mark.asyncio
async def testChatPageRendersWithSummaryPanel(chatApp):
    transport = ASGITransport(app=chatApp)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
    assert "summaryContent" in response.text
    assert 'sse-swap="summary-update"' in response.text
