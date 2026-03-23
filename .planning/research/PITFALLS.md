# Domain Pitfalls

**Domain:** Multi-Agent LLM Expense Claims Automation
**Researched:** 2026-03-23

## Critical Pitfalls

Mistakes that cause rewrites or major issues.

### Pitfall 1: Multi-Agent Coordination Breakdowns
**What goes wrong:** Multi-agent LLM systems experience failure rates ranging from 41% to 86.7%, with coordination breakdowns representing 36.9% of all failures. Unstructured multi-agent networks can amplify errors up to 17.2 times compared to single-agent baselines.

**Why it happens:** Inter-agent misalignment - agents fail to communicate effectively, proceed with wrong assumptions instead of seeking clarification, withhold crucial information (0.85%), ignore other agents' input (1.90%), or have mismatches between reasoning and action (13.2%).

**Consequences:** Task derailment (7.4%), unexpected conversation resets (2.2%), invalid outputs submitted to end users, complete system failure requiring manual intervention.

**Prevention:**
- Design explicit communication protocols between agents
- Implement validation gates between agent handoffs (verify input matches expected schema before processing)
- Use LangGraph's shared state with typed schemas to enforce alignment
- Tag agent outputs with confidence scores for downstream validation
- Implement retry logic with explicit clarification requests when assumptions are uncertain

**Detection:**
- Monitor task completion rates by agent handoff point (identify which transitions fail)
- Track agent-to-agent message schemas for type mismatches
- Log instances where agent B asks agent A to repeat/clarify (signal of poor initial communication)
- Measure output quality degradation after multiple agent hops

**Phase mapping:** Address in Phase 1 (Core Architecture) - establish state schema and agent communication contracts upfront.

### Pitfall 2: LangGraph State Explosion and Serialization Failures
**What goes wrong:** Checkpoint database grows indefinitely due to large state objects (base64-encoded receipts, PDF data) causing memory errors, slow serialization, and eventual database crashes. A critical remote code execution vulnerability (CVE-2025-XXXX) existed in LangGraph checkpoint serialization before version 3.0.

**Why it happens:**
- No TTL configured - old checkpoints accumulate indefinitely
- Receipt images stored directly in state as base64 (100KB+ per image * hundreds of claims)
- Subgraphs with separate checkpointers create duplicate storage
- InjectedState in tools contains non-serializable objects (fails on json.dumps)

**Consequences:**
- OOM errors in production after processing ~50-100 claims
- Database disk usage grows from MB to GB in days
- 3-5 second latency per state checkpoint (blocks agent execution)
- Security vulnerability allowing arbitrary code execution

**Prevention:**
- Upgrade to langgraph-checkpoint >= 3.0.0 immediately (security patch)
- Configure TTL for checkpoints (7-day retention for completed claims, 1-day for abandoned sessions)
- Store receipts in external object storage (S3/filesystem), keep only file paths in state
- Use small, typed, validated state objects (< 10KB per checkpoint)
- Redirect all logs to stderr (stdout pollution causes Error -32000, accounting for 97% of MCP failures)
- Avoid InjectedState in tool definitions - pass state explicitly via function arguments

**Detection:**
- Monitor checkpoint table size daily (alert if > 1GB or growth > 100MB/day)
- Track checkpoint serialization time (alert if p95 > 500ms)
- Log state object sizes before checkpoint (warn if > 50KB)
- Watch pod memory usage during checkpoint operations

**Phase mapping:** Address in Phase 2 (Receipt Processing) - this is when large binary data enters the system.

### Pitfall 3: VLM Receipt Extraction Hallucinations
**What goes wrong:** VLMs hallucinate on low-quality receipt images, producing fluent but incorrect extraction results without signaling uncertainty. Open-source VLM models show limited reasoning capacity and low precision, returning random hallucinated data. Mistral OCR has a 50% character error rate and refuses to process 30% of images.

**Why it happens:**
- No confidence scoring in VLM outputs (unlike traditional OCR which provides per-character confidence)
- Visually degraded images (crumpled receipts, faded ink, poor lighting)
- Multi-language receipts not in training data
- Model attempts to complete incomplete information rather than admitting uncertainty

**Consequences:**
- 15-20% information extraction error rate compounds into invalid claims
- Finance team wastes time manually verifying every extracted field
- False positives (approved invalid claims) create audit/compliance risks
- User frustration when system confidently extracts wrong amounts

**Prevention:**
- Use prompt engineering to instruct VLM to return "UNCERTAIN" for low-quality fields
- Implement structured output validation with Pydantic (reject responses missing required fields)
- Hybrid approach: VLM extracts, then rule-based validation checks (e.g., total = sum(line items))
- Request multiple VLM passes and compare outputs (flag discrepancies for human review)
- Pre-process images with quality checks (reject blurry/low-resolution images before VLM call)
- For production: Use GPT-4o (25% CER) or Gemini 2.0 Flash (15% CER), avoid Mistral OCR (50% CER)
- Zero-cost constraint: Accept higher error rates with free models, invest in validation instead

**Detection:**
- Track extraction confidence by field (flag claims where >2 fields marked uncertain)
- Compare extracted totals vs line item sums (mathematical inconsistency = hallucination signal)
- Monitor user edit rates per field (if users edit "merchant" 40% of the time, VLM is unreliable)
- A/B test: Re-extract same receipt twice, measure consistency

**Phase mapping:** Address in Phase 2 (Receipt Processing) - build validation pipeline in parallel with VLM extraction.

### Pitfall 4: RAG Policy Retrieval Returns Irrelevant Chunks
**What goes wrong:** RAG retrieval returns policy chunks that don't answer the validation question, causing agents to make incorrect approval decisions. Character-based splitting breaks policy rules mid-sentence, mixing unrelated rules in the same chunk.

**Why it happens:**
- Naive chunking breaks logical boundaries (e.g., "Travel expenses over $500 require..." cut off from "...manager approval")
- Chunk size too small (< 250 tokens) loses context ("Singapore branch" separated from its rules)
- Chunk size too large (> 1000 tokens) dilutes relevance (multiple policy topics compressed into one vector)
- No overlap between chunks causes context loss at boundaries
- Embedding model doesn't understand domain-specific terms ("per diem", "reimbursable", "pre-approval")

**Consequences:**
- Agent approves expense that violates policy (chunk didn't include the restriction)
- Agent rejects valid expense (retrieved chunk from wrong policy section)
- User loses trust in system ("It rejected my lunch expense, but that's explicitly allowed in Section 3.2")

**Prevention:**
- Use semantic chunking or recursive character splitting at 400-512 tokens with 10-20% overlap (2026 benchmark winner)
- For policy documents: Hierarchical chunking that preserves section structure
- Add metadata to chunks (section title, policy category) for filtered retrieval
- Implement chunk context enrichment: Prepend section header to each chunk before embedding
- Test retrieval with edge cases: "What's the limit for Singapore meals?" should retrieve Singapore-specific rules
- Use reranking after initial retrieval (cross-encoder reranks top-k chunks by relevance)
- Configure Qdrant with pre-filtering for low-latency retrieval (prevents p99 latency spikes)

**Detection:**
- Manual spot-checks: Given query "Can I claim dinner over $100?", verify correct policy section retrieved
- Track retrieval-to-validation consistency: If agent asks "Is meal allowed?" but retrieves travel policy, flag mismatch
- Monitor user appeals: "System rejected my claim, but policy says it's OK" = retrieval failure
- Measure chunk boundary splits: Alert if policy rules span multiple chunks without overlap

**Phase mapping:** Address in Phase 1 (RAG Infrastructure) - chunking strategy affects all downstream policy validation.

### Pitfall 5: OpenRouter Free Model Rate Limits Break Production
**What goes wrong:** Free model rate limits (20 req/min, 50-200 req/day) are insufficient for multi-agent systems where each claim triggers 5-10 LLM calls. During peak times, free requests queue behind paid requests, causing 30-60 second delays. Failed attempts still count toward quota.

**Why it happens:**
- Zero-cost constraint forces use of free models
- Multi-agent architecture multiplies LLM calls (receipt extraction + policy lookup + validation + justification)
- Peak usage (end of month expense submissions) exceeds daily quota by 10x
- No retry backoff strategy when rate limited

**Consequences:**
- Users wait 2+ minutes for claim processing
- System becomes unusable during month-end
- Incomplete claim processing (agent stops mid-workflow when quota exceeded)
- Poor user experience drives manual submission instead

**Prevention:**
- Budget for paid tier: Even $10/month unlocks 1000 req/day (20x increase)
- If staying free: Implement aggressive caching (cache policy RAG results, don't re-embed identical receipts)
- Batch operations where possible (extract all line items in single VLM call vs one call per item)
- Implement exponential backoff with queue system (show user estimated wait time)
- Use cheaper models for non-critical tasks (free model for draft, paid model for final validation)
- Synthetic policy generation: Pre-compute common policy Q&A, use retrieval instead of LLM call
- Design for async: Don't block user on LLM responses, process in background and notify when complete

**Detection:**
- Monitor OpenRouter API response codes (track rate limit errors per day)
- Track requests per claim (optimize if > 8 calls per claim)
- Measure processing time p95 (alert if > 30 seconds)
- User drop-off rate at submission (if users abandon after clicking submit, latency is too high)

**Phase mapping:** Address in Phase 1 (Infrastructure) - establish API rate limiting strategy before building agents.

## Moderate Pitfalls

Mistakes that cause delays or technical debt.

### Pitfall 6: MCP Server Protocol Compliance Failures
**What goes wrong:** Error -32000 accounts for 97% of MCP connection failures. MCP servers print to stdout causing protocol violations. Wrong transport type (HTTP vs SSE vs stdio) causes connection timeouts.

**Why it happens:**
- Logging to stdout instead of stderr (MCP protocol requires clean stdout for JSON-RPC messages)
- Node.js version < 18 causes protocol incompatibilities (2026 standard is Node 22 LTS)
- Misconfigured transport in client (Chainlit expects stdio, server configured for HTTP)

**Prevention:**
- Force all logging to stderr in MCP server implementations
- Use absolute paths for Node.js/Python executables in MCP config
- Test MCP servers with `claude mcp test` command before integration (v1.0.33+)
- Match transport type between client and server configs
- Pin Node.js 22 LTS in Docker containers

**Detection:**
- MCP connection health checks (ping server on startup)
- Parse error codes: -32000 = stdout pollution, 406 = transport mismatch, ENOENT = path issue

**Phase mapping:** Address in Phase 1 (MCP Infrastructure) - establish MCP server patterns before building tools.

### Pitfall 7: Chainlit + LangGraph Dependency Conflicts
**What goes wrong:** Chainlit 2.0.4 requires uvicorn (<0.26.0) while langgraph-api 0.0.16 requires uvicorn (>=0.26.0), causing installation failures. LangGraph streaming within Chainlit decreases UI responsiveness.

**Why it happens:**
- Incompatible dependency pinning between frameworks
- LangGraph's astream_events produces events faster than Chainlit can render
- Async/sync mismatches (LangGraph graph is sync, Chainlit steps are async)

**Prevention:**
- Use separate Docker services: Chainlit UI container + LangGraph API container (avoid direct dependency)
- If integrating directly: Lock compatible versions (test before deploying)
- Implement event throttling: Buffer LangGraph events, render every 500ms vs real-time
- Use Chainlit's LangchainCallbackHandler for proper event filtering
- Tag LangGraph nodes to filter events (only stream user-facing steps, suppress internal coordination)

**Detection:**
- Dependency conflict errors during `pip install`
- UI freezes or stuttering during agent execution
- Missing events in Chainlit UI (indicates dropped events)

**Phase mapping:** Address in Phase 1 (UI Integration) - resolve dependency conflicts before building conversational interface.

### Pitfall 8: Qdrant Memory Management Failures
**What goes wrong:** Qdrant's on_disk=True doesn't fully solve RAM issues. Production deployments with millions of vectors crash despite disk persistence. Inserting large point batches causes performance degradation.

**Why it happens:**
- Qdrant keeps metadata and indexes in memory even when vectors on disk
- Batch insertion without rate limiting overwhelms memory allocator
- No pre-filtering configured, causing p99 latency spikes at low selectivity

**Prevention:**
- Configure memory limits in Qdrant (limit in-memory cache size)
- Batch insertions at 500-1000 points max per request
- Use pre-filtering (single-stage filtering) for policy retrieval (filter by policy category before vector search)
- Monitor memory usage under load (load test with 10K+ policy chunks before production)
- For resource-constrained deployments: Qdrant is optimal, but requires careful tuning

**Detection:**
- Track Qdrant memory usage during ingestion (alert if > 80% of pod limit)
- Measure p99 retrieval latency (degrade if > 200ms)
- Monitor failed insertion requests

**Phase mapping:** Address in Phase 2 (RAG Infrastructure) - load test during policy document ingestion.

## Minor Pitfalls

Mistakes that cause annoyance but are fixable.

### Pitfall 9: Docker Networking for Local MCP Servers
**What goes wrong:** MCP servers in Docker containers can't connect to host services (Qdrant, Postgres) using localhost.

**Why it happens:**
- localhost inside container != localhost on host machine
- Docker network isolation

**Prevention:**
- Use host.docker.internal for Mac/Windows Docker Desktop
- Use docker-compose networking with service names (mcp-server connects to qdrant:6333)
- Document network configuration in docker-compose.yml

**Detection:**
- Connection refused errors in MCP server logs
- MCP server starts but tools fail when invoked

**Phase mapping:** Address in Phase 1 (Docker Setup) - establish networking patterns in docker-compose.yml.

### Pitfall 10: Missing LangGraph Recursion Limits
**What goes wrong:** Agent enters infinite loop when validation fails repeatedly. Graph executes until manual interruption.

**Why it happens:**
- No termination condition in conditional edges
- No recursion_limit set on graph invocation

**Prevention:**
- Set recursion_limit=50 (or lower) on graph.invoke()
- Implement explicit termination nodes ("max retries exceeded")
- Use counters in state to track loop iterations

**Detection:**
- Graph execution time exceeds expected threshold (alert if > 60 seconds)
- Same node executes >10 times in single run

**Phase mapping:** Address in Phase 3 (Agent Logic) - add safety limits during agent development.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Phase 1: Infrastructure Setup | MCP Protocol Compliance (Error -32000), OpenRouter Rate Limits, Chainlit Dependencies | Establish MCP logging patterns (stderr only), budget $10 for paid tier or design for async processing, use Docker service separation |
| Phase 2: Receipt Processing | VLM Hallucinations, LangGraph State Explosion | Build validation pipeline in parallel with extraction, store receipts externally with path references |
| Phase 3: RAG Policy Validation | Irrelevant Chunk Retrieval, Qdrant Memory Issues | Use semantic chunking at 400-512 tokens, load test with 10K+ chunks, implement reranking |
| Phase 4: Multi-Agent Coordination | Inter-Agent Misalignment, Coordination Failures | Design typed state schemas upfront, validate handoffs between agents, monitor completion rates by transition |
| Phase 5: Production Deployment | State Database Growth, Rate Limit Exhaustion | Configure checkpoint TTL (7-day retention), implement caching for repeated queries, monitor API quotas |

## Sources

- [LangGraph Explained (2026 Edition) - Medium](https://medium.com/@dewasheesh.rana/langgraph-explained-2026-edition-ea8f725abff3)
- [LangGraph: Build Stateful Multi-Agent Systems That Don't Crash](https://www.mager.co/blog/2026-03-12-langgraph-deep-dive/)
- [LangGraph Best Practices - Swarnendu De](https://www.swarnendu.de/blog/langgraph-best-practices/)
- [Critical Flaw in LangGraph Allows Remote Code Execution via Deserialization](https://cyberpress.org/flaw-in-langgraph/)
- [Use the graph API - LangChain Docs](https://docs.langchain.com/oss/python/langgraph/use-graph-api)
- [Unlocking AI Resilience: Mastering State Persistence with LangGraph and PostgreSQL](https://dev.to/programmingcentral/unlocking-ai-resilience-mastering-state-persistence-with-langgraph-and-postgresql-50h0)
- [State Management in LangGraph: The Foundation of Reliable AI Workflows](https://medium.com/algomart/state-management-in-langgraph-the-foundation-of-reliable-ai-workflows-db98dd1499ca)
- [From Brittle to Brilliant: Why We Replaced OCR with VLMs](https://www.trmlabs.com/resources/blog/from-brittle-to-brilliant-why-we-replaced-ocr-with-vlms-for-image-extraction)
- [Document Data Extraction in 2026: LLMs vs OCRs](https://www.vellum.ai/blog/document-data-extraction-llms-vs-ocrs)
- [Best Vision Language Models for Document Data Extraction](https://nanonets.com/blog/vision-language-model-vlm-for-data-extraction/)
- [Teaching VLMs to Admit Uncertainty in OCR from Lossy Visual Inputs - OpenReview](https://openreview.net/forum?id=zyCjizqOxB)
- [RAG Chunking Strategies: The 2026 Benchmark Guide](https://blog.premai.io/rag-chunking-strategies-the-2026-benchmark-guide/)
- [Chunking Strategies for RAG: Best Practices - Unstructured](https://unstructured.io/blog/chunking-for-rag-best-practices)
- [Best Chunking Strategies for RAG (and LLMs) in 2026](https://www.firecrawl.dev/blog/best-chunking-strategies-rag)
- [MCP Server Troubleshooting: Common Errors Fix (2026)](https://mcpplaygroundonline.com/blog/mcp-server-troubleshooting-common-errors-fix)
- [MCP Error Codes - mcpevals.io](https://www.mcpevals.io/blog/mcp-error-codes)
- [Error Handling And Debugging MCP Servers - Stainless](https://www.stainless.com/mcp/error-handling-and-debugging-mcp-servers)
- [Why Do Multi-Agent LLM Systems Fail? - arXiv](https://arxiv.org/abs/2503.13657)
- [Why Your Multi-Agent System is Failing: The 17x Error Trap](https://towardsdatascience.com/why-your-multi-agent-system-is-failing-escaping-the-17x-error-trap-of-the-bag-of-agents/)
- [Why Multi-Agent LLM Systems Fail (and How to Fix Them)](https://www.augmentcode.com/guides/why-multi-agent-llm-systems-fail-and-how-to-fix-them)
- [What ICLR 2026 Taught Us About Multi-Agent Failures](https://llmsresearch.substack.com/p/what-iclr-2026-taught-us-about-multi)
- [OpenRouter Free Models: All 27 Listed (Mar 2026)](https://costgoat.com/pricing/openrouter-free-models)
- [OpenRouter Rate Limits – What You Need to Know](https://openrouter.zendesk.com/hc/en-us/articles/39501163636379-OpenRouter-Rate-Limits-What-You-Need-to-Know)
- [29 Free AI Models on OpenRouter (March 2026)](https://www.teamday.ai/blog/best-free-ai-models-openrouter-2026)
- [LangChain/LangGraph - Chainlit Docs](https://docs.chainlit.io/integrations/langchain)
- [Dependency issue with langgraph - Chainlit Issue #1737](https://github.com/Chainlit/chainlit/issues/1737)
- [Enhanced LangGraph Streaming Support - Chainlit Issue #1393](https://github.com/Chainlit/chainlit/issues/1393)
- [Best vector databases for production RAG in 2026](https://engineersguide.substack.com/p/best-vector-databases-rag)
- [The Hidden Bottleneck of RAG: Why Your Vector Database is Crashing](https://medium.com/@Chirag_writes/the-hidden-bottleneck-of-rag-why-your-vector-database-is-crashing-your-pipeline-8402d15f78fa)
- [Qdrant vs pgvector: Same Speed. The Bottleneck Isn't the Vector DB](https://medium.com/@TheWake/qdrant-vs-pgvector-theyre-the-same-speed-5ac6b7361d9d)
- [The Architecture of Agent Memory: How LangGraph Really Works](https://dev.to/sreeni5018/the-architecture-of-agent-memory-how-langgraph-really-works-59ne)
- [Understanding Checkpointers, Databases, API Memory - LangChain Support](https://support.langchain.com/articles/6253531756-understanding-checkpointers-databases-api-memory-and-ttl)
