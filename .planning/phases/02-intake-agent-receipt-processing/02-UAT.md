---
status: complete
phase: 02-supporting-infrastructure
source: [02-01-SUMMARY.md, 02-02-SUMMARY.md]
started: 2026-03-24T02:15:00Z
updated: 2026-03-24T03:00:00Z
---

## Current Test

number: complete
name: All tests completed
status: done

## Tests

### 1. All Docker services healthy
expected: Run `docker compose ps` — all 7 services show **(healthy)** status: app, postgres, qdrant, mcp-rag, mcp-db, mcp-currency, mcp-email
result: pass

### 2. Database tables exist in Postgres
expected: Run `docker compose exec postgres psql -U agentic -d agentic_claims -c '\dt'` — shows 3 tables: claims, receipts, audit_log (plus alembic_version)
result: pass

### 3. Alembic migration applied
expected: Run `docker compose exec app poetry run alembic current` inside app container — shows migration 001 as head (not empty)
result: issue
reported: "Dockerfile missing alembic.ini and alembic/ directory. POSTGRES_HOST=localhost wrong inside container. Postgres password out of sync with volume. Tables existed but Alembic not stamped."
severity: major

### 4. Policy documents ingested in Qdrant
expected: Run `curl http://localhost:6333/collections/expense_policies` — collection exists with 35 points, vector size 384, status "green"
result: pass

### 5. Semantic policy search returns relevant results
expected: Run `curl -X POST http://localhost:6333/collections/expense_policies/points/search -H 'Content-Type: application/json' -d '{"vector": [0.1]*384, "limit": 1}'` OR use the RAG MCP server — returns a policy chunk with category and section metadata (not just raw text)
result: pass
note: Used qdrant-client query_points() API (search() removed in 1.17.1). Returned meals.md Section 2 with score 0.5441.

### 6. MCP RAG server accepting connections
expected: Run `curl -s http://localhost:8001/mcp` — returns an HTTP response (any status code like 405/406, NOT a connection hang or timeout). This confirms the Streamable HTTP transport is running.
result: pass
note: Initially returned 000 (connection refused). Root cause: FastMCP binds to 127.0.0.1 by default. Fixed by adding FASTMCP_HOST=0.0.0.0 to docker-compose.yml. Now returns 406.

### 7. MCP DB server can query database
expected: The DB MCP server at port 8002 is running and responds to HTTP requests on /mcp endpoint (returns 405/406 immediately, no hang)
result: pass
note: Returns 406 after FASTMCP_HOST fix.

### 8. MCP Currency server responds
expected: The Currency MCP server at port 8003 is running and responds on /mcp endpoint (returns 405/406 immediately)
result: pass
note: Returns 406 after FASTMCP_HOST fix.

### 9. MCP Email server responds
expected: The Email MCP server at port 8004 is running and responds on /mcp endpoint (returns 405/406 immediately)
result: pass
note: Returns 406 after FASTMCP_HOST fix.

### 10. Test suite passes
expected: Run `poetry run pytest tests/ -v` — all 22 tests pass (7 database, 3 graph, 7 OpenRouter, 5 policy ingestion), 0 failures
result: pass
note: 22 passed in 6.52s. 1 deprecation warning (langchain_core Pydantic V1 on Python 3.14).

## Summary

total: 10
passed: 9
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "Alembic migration runs inside Docker container and shows 001 as head"
  status: failed
  reason: "User reported: Dockerfile missing alembic.ini and alembic/ directory. POSTGRES_HOST=localhost wrong inside container. Postgres password out of sync with volume. Tables existed but Alembic not stamped."
  severity: major
  test: 3
  root_cause: "Dockerfile didn't COPY alembic.ini or alembic/. Docker-compose didn't override POSTGRES_HOST for Docker network. Postgres volume initialized before .env.local credentials set. Executor created tables via raw SQL but didn't run alembic stamp."
  artifacts:
    - path: "Dockerfile"
      issue: "Missing COPY alembic.ini and COPY alembic/"
    - path: "docker-compose.yml"
      issue: "App service missing POSTGRES_HOST=postgres and QDRANT_HOST=qdrant overrides"
  missing:
    - "Alembic stamp head after table creation"
  debug_session: ""
