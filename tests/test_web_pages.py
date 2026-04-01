"""Smoke tests for all 4 page routes and session cookie."""

import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient


@pytest.fixture
def client():
    """TestClient with mocked lifespan (no DB required)."""
    # Ensure test env vars are set before import
    os.environ.setdefault("SESSION_SECRET_KEY", "test-secret-key")

    # Mock getCompiledGraph to avoid DB connection during import
    with patch("agentic_claims.core.graph.getCompiledGraph") as mockGetGraph:
        mockGraph = AsyncMock()
        mockCheckpointerCtx = AsyncMock()
        mockGetGraph.return_value = (mockGraph, mockCheckpointerCtx)

        # Now import the app — getSettings() will load from .env.test via conftest
        from agentic_claims.web.main import app

        with TestClient(app) as c:
            yield c


def testChatPageReturns200(client):
    """GET / returns 200 with chat page content."""
    response = client.get("/")
    assert response.status_code == 200
    assert "AI Expense Submission" in response.text


def testDashboardPageReturns200(client):
    """GET /dashboard returns 200 with dashboard page content."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Approver Dashboard" in response.text


def testAuditPageReturns200(client):
    """GET /audit returns 200 with audit page content."""
    response = client.get("/audit")
    assert response.status_code == 200
    assert "Audit" in response.text


def testReviewPageReturns200(client):
    """GET /review/test-claim-123 returns 200 with claim ID."""
    response = client.get("/review/test-claim-123")
    assert response.status_code == 200
    assert "test-claim-123" in response.text


def testSessionCookieSetOnFirstVisit(client):
    """GET / sets agentic_session cookie."""
    response = client.get("/")
    assert response.status_code == 200
    cookies = response.cookies
    assert "agentic_session" in cookies


def testActivePageIndicatorChat(client):
    """GET / shows active indicator for chat nav item."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text-[#62fae3]" in response.text


def testActivePageIndicatorDashboard(client):
    """GET /dashboard shows active indicator for dashboard nav item."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "text-[#62fae3]" in response.text


def test404ForUnknownRoute(client):
    """GET /nonexistent returns 404."""
    response = client.get("/nonexistent")
    assert response.status_code == 404
