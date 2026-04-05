# ReAct Agent Prompt Design: Technical Research

**Date**: 2026-04-03
**Context**: Intake agent in a LangGraph expense claims system hallucinated a claim submission (CLAIM-1523) without calling `submitClaim`. Logs showed "0 tools called". This research investigates prompt design patterns to prevent this class of failure.

## Strategic Summary

The hallucinated submission is a **tool selection hallucination** -- the agent narrated a tool call instead of executing one. Research shows this failure mode has three compounding causes: (1) prompt structure that does not create strong enough causal dependencies between tool calls and reported outcomes, (2) absence of infrastructure-level validation that the tool was actually called before the agent claims success, and (3) negative constraints ("NEVER generate a claim number") that models process less reliably than positive instructions. The fix requires changes at both the prompt level (restructured phases with explicit precondition checks) and the infrastructure level (post-response validation in `intakeNode`). OpenAI's GPT-4.1 guide, Anthropic's agent-building guide, and AWS's hallucination prevention research converge on the same principle: prompts are suggestions, not constraints -- critical invariants must be enforced in code.

---

## 1. Prompt Structure for LangGraph ReAct Agents

### How `create_react_agent`'s `prompt` Parameter Works

The `prompt` parameter accepts:
- A **string** -- prepended as a system message before the conversation
- A **`SystemMessage`** instance -- allows structured content blocks and cache control (LangChain v1.1.0+)
- **`None`** (default) -- the agent infers its task from messages directly

```python
# String prompt (current usage)
agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt="You are a helpful assistant. Always be concise.",
)

# SystemMessage prompt (enables cache control)
from langchain.messages import SystemMessage
agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=SystemMessage(content="You are a helpful assistant."),
)
```

The prompt is injected as the first message in every LLM call within the ReAct loop. The agent then cycles: LLM reasons -> selects tool -> tool executes -> observation fed back -> LLM reasons again -> until no more tool calls are generated.

**Key finding**: The `prompt` parameter is a static string. It cannot dynamically adapt based on what tools have already been called in the current invocation. Phase-awareness must be encoded through instructions that tell the agent to inspect its own conversation history.

### Recommended Section Order for ReAct System Prompts

Based on convergent findings from OpenAI's GPT-4.1 guide, Anthropic's agent-building guide, and production agent prompt research:

```
1. IDENTITY & ROLE          -- Who you are, one sentence
2. PERSISTENCE DIRECTIVE     -- "Keep going until the task is fully resolved"
3. TOOL-CALLING DISCIPLINE   -- "Use tools to gather information, do NOT guess"
4. TOOLS REFERENCE           -- Tool names, signatures, when to use each
5. WORKFLOW / PHASES         -- Sequential steps with explicit preconditions
6. OUTPUT FORMAT             -- How to present results to the user
7. CONSTRAINTS               -- Positive-framed rules (max 3-5)
8. ERROR HANDLING            -- How to recover from tool failures
```

**Why this order matters**: Models attend most strongly to the beginning of the system prompt and to user messages. The identity, persistence, and tool-calling discipline sections establish the behavioral frame before any specific instructions. OpenAI found that placing "You are an agent" + "keep going until resolved" + "use tools, do NOT guess" at the top increased SWE-bench Verified scores by ~20%.

**Current prompt gap**: The existing intake prompt leads with ARCHITECTURE (UI rendering details) before establishing tool-calling discipline. The MANDATORY TOOL USAGE section is buried after output format instructions.

### Sources
- [LangGraph create_react_agent docs](https://docs.langchain.com/oss/python/langgraph)
- [LangGraph prebuilt README](https://github.com/langchain-ai/langgraph/blob/main/libs/prebuilt/README.md)
- [LangChain v1.1.0 changelog -- SystemMessage support](https://docs.langchain.com/oss/python/langgraph/changelog-py)
- [OpenAI GPT-4.1 Prompting Guide](https://developers.openai.com/cookbook/examples/gpt4-1_prompting_guide)

---

## 2. Phase-Gated Process Enforcement in Multi-Turn Conversations

### The Core Challenge

The agent must follow a strict Extract -> Policy Check -> Submit workflow across multiple conversation turns. The current prompt encodes phases through CONVERSATION STATE AWARENESS instructions that tell the agent to check its own history. This is the right approach -- but the preconditions are too loosely specified.

### Pattern: Explicit Precondition Gates

The most effective pattern from production systems is **precondition-based gating** where each phase lists what MUST be true (verifiable from conversation history) before the phase can begin.

```
### Phase 3: Submit
PRECONDITIONS (all must be true before you begin this phase):
- extractReceiptFields tool was called and returned a result (check your tool call history)
- searchPolicies tool was called and returned a result (check your tool call history)  
- User explicitly confirmed submission (said "yes", "confirm", "submit", or equivalent)
- Employee ID is a concrete value (not a placeholder)

If ANY precondition is not met, you CANNOT proceed to this phase.
Ask the user for what is missing.
```

**Why this works better than the current approach**: The current prompt says "searchPolicies was called, user confirmed submission -> Phase 3 (submit)". This is a detection rule ("if X, then Phase 3"). The precondition pattern inverts it: "before Phase 3, verify X, Y, Z". The inversion forces the model to actively check rather than passively match.

### Pattern: Tool-Call History Verification

```
Before calling submitClaim, verify ALL of these in your conversation history:
1. You can find a ToolMessage with name="extractReceiptFields" 
2. You can find a ToolMessage with name="searchPolicies"
3. The user's most recent message contains explicit confirmation

If you cannot find evidence of ALL three, STOP and complete the missing phases first.
```

This pattern works because it grounds phase detection in concrete, verifiable artifacts (ToolMessage objects in the conversation) rather than abstract state tracking.

### Pattern: Phase Labeling in Responses

Some production systems require the agent to explicitly declare its phase at the start of each response:

```
Begin each response with an internal phase declaration:
[PHASE: Extract] or [PHASE: PolicyCheck] or [PHASE: Submit]

This helps you track where you are in the workflow.
```

**Tradeoff**: Adds tokens to every response but significantly improves phase tracking accuracy. Can be hidden from the user via the UI layer.

### Anthropic's Workflow Patterns

Anthropic's "Building Effective Agents" guide distinguishes between **workflows** (predefined paths) and **agents** (dynamic decision-making). For the intake use case, the correct pattern is **prompt chaining with programmatic gates**:

> "Prompt chaining decomposes a task into a sequence of steps, where each LLM call processes the output of the previous one. You can add programmatic checks ('gates') on any intermediate steps to ensure that the process is still on track."

This suggests that the strongest enforcement comes from infrastructure-level checks (in `intakeNode`), not from prompt instructions alone.

### Sources
- [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [AWS: Prompt Chaining Workflow Pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-patterns/workflow-for-prompt-chaining.html)
- [Deepchecks: Multi-Step LLM Chains Best Practices](https://deepchecks.com/orchestrating-multi-step-llm-chains-best-practices/)

---

## 3. Tool-Usage Discipline & Hallucination Prevention

### Why ReAct Agents Skip Tools and Fabricate Results

Research identifies two distinct failure modes (from "Reducing Tool Hallucination via Reliability Alignment", arXiv 2412.04141):

1. **Tool Selection Hallucination**: The model chooses not to call the tool, or calls a nonexistent tool. This is what happened with the CLAIM-1523 incident -- the model narrated a submission instead of calling `submitClaim`.

2. **Tool Usage Hallucination**: The model calls the correct tool but with fabricated parameters (e.g., inventing a claim number as an input).

**Root causes for tool-skipping**:
- The model has seen many training examples where it can answer directly, so the prior for "just respond" is strong
- Long conversation histories push tool definitions out of the attention window
- Insufficient emphasis in the prompt that certain outcomes are IMPOSSIBLE without tool calls
- The model may believe it already has enough information to respond (the "completion bias")

### Pattern: Causal Impossibility Statements

Instead of "NEVER generate a claim number", use causal language that makes the fabrication logically impossible:

```
Claim numbers are generated by the database when submitClaim executes.
They do not exist until the database creates them.
You have no way to know a claim number without calling submitClaim and reading its response.
```

This works better than prohibitions because it gives the model a causal model of reality, not just a rule to follow. The model understands "I literally cannot know X without doing Y" more reliably than "I should not say X without doing Y".

### Pattern: Neurosymbolic Guardrails (Infrastructure-Level)

The strongest pattern from AWS's hallucination prevention research: validate tool calls at the infrastructure level, not in the prompt.

```python
# In intakeNode, after agent completes
def validateSubmissionClaim(resultMessages):
    """Verify submitClaim was actually called before agent claims submission."""
    agentClaimsSubmission = False
    submitToolCalled = False
    
    for msg in resultMessages:
        # Check if agent's final response mentions submission
        if hasattr(msg, "content") and isinstance(msg.content, str):
            if any(phrase in msg.content.lower() for phrase in [
                "submitted successfully", "claim submitted", "has been submitted"
            ]):
                agentClaimsSubmission = True
        
        # Check if submitClaim tool was actually called
        if hasattr(msg, "name") and msg.name == "submitClaim":
            submitToolCalled = True
    
    if agentClaimsSubmission and not submitToolCalled:
        # HALLUCINATION DETECTED -- agent claimed submission without tool call
        return True  # needs intervention
    return False
```

**Key insight from the research**: "Prompts are suggestions, not constraints. Agents ignore docstring rules because they're processed as text, not executable logic." (AWS hallucination prevention guide). The only way to guarantee a tool was called is to check programmatically.

### Pattern: Semantic Tool Filtering

When agents have access to many tools, hallucination rates increase. Research shows reducing visible tools from 31 to 3 (the relevant ones) reduced errors by 86.4%. For the intake agent with 5 tools, this is less of a concern, but the principle applies: tool descriptions should be clear enough that the model never confuses which tool does what.

### Tradeoffs

| Approach | Reliability | Complexity | Latency |
|----------|------------|------------|---------|
| Causal impossibility statements in prompt | Medium-High | Low | None |
| Precondition gates in prompt | Medium | Low | None |
| Infrastructure validation in intakeNode | High | Medium | Negligible |
| Multi-agent validation (executor + validator) | Highest | High | 2x+ |

For the intake agent, the right combination is causal impossibility statements + infrastructure validation. Multi-agent validation is overkill for a single tool-call check.

### Sources
- [Reducing Tool Hallucination via Reliability Alignment (arXiv)](https://arxiv.org/html/2412.04141v1)
- [AWS: Stop AI Agent Hallucinations: 4 Essential Techniques](https://dev.to/aws/stop-ai-agent-hallucinations-4-essential-techniques-2i94)
- [Anthropic: Writing Tools for Agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Anthropic: Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)
- [Tool Receipts for Hallucination Detection (arXiv)](https://arxiv.org/html/2603.10060v1)

---

## 4. Tool-Then-Speak Sequencing

### The Problem

The agent generated text like "Your claim CLAIM-1523 has been submitted successfully" without ever calling `submitClaim`. It narrated the tool call instead of making it. This is the "speak instead of act" failure mode.

### Pattern: Causal Dependency Phrasing

The most effective prompt pattern establishes that certain information is causally impossible to know without a tool call:

```
## SUBMISSION RULES

The submitClaim tool is the ONLY way to create a claim in the database.
When you call submitClaim, the database generates a unique claim number (CLAIM-NNN).
This claim number does not exist anywhere until the database creates it.

To confirm submission to the user, you MUST:
1. Call submitClaim with the complete claim data
2. Read the claim number from the submitClaim response
3. Include that exact claim number in your confirmation message

You cannot confirm submission without completing step 1.
You cannot reference a claim number without completing step 2.
```

### OpenAI's Warning About Forced Tool Calls

OpenAI's GPT-4.1 guide explicitly warns against unconditional tool-call mandates:

> "If told 'you must call a tool before responding to the user,' models may hallucinate tool inputs or call the tool with null values if they do not have enough information."

The recommended mitigation: "Add 'if you don't have enough information to call the tool, ask the user for the information you need.'"

This means the prompt should not say "you MUST call submitClaim" unconditionally. Instead:

```
When the user confirms submission AND you have all required data:
1. Call submitClaim with the claim data
2. Report the result

When you do NOT have all required data:
1. Tell the user what is missing
2. Ask them to provide it

You CANNOT confirm a submission without a successful submitClaim response.
```

### Pattern: Forcing Tool Calls at the API Level

Both OpenAI and Anthropic support `tool_choice` parameters:

| Setting | Behavior |
|---------|----------|
| `auto` (default) | Model decides whether to call a tool |
| `required` / `any` | Model MUST call at least one tool |
| `{"name": "submitClaim"}` | Model MUST call this specific tool |

**Limitation for LangGraph**: `create_react_agent` does not expose `tool_choice` per-turn. The ReAct loop always uses `auto` because the agent needs to decide on each iteration whether to call another tool or respond. Forcing `tool_choice: required` would break the loop termination.

However, there is a workaround: bind tool_choice on the model itself for specific steps:

```python
# Force a specific tool call (from LangGraph SQL agent example)
llm_with_forced_tool = model.bind_tools([submit_tool], tool_choice="any")
response = llm_with_forced_tool.invoke(messages)
```

This is not directly applicable to `create_react_agent` but could be used if the agent is rebuilt with a custom graph.

### Pattern: Post-Response Validation

The most robust approach: validate after the agent responds, before sending to the user.

```python
# In intakeNode or app.py, after agent.ainvoke()
finalMessage = result["messages"][-1]
if mentionsSubmission(finalMessage) and not toolWasCalled(result["messages"], "submitClaim"):
    # Replace the hallucinated response
    correctedMessage = AIMessage(
        content="I need to complete the submission process. Let me submit your claim now."
    )
    # Re-invoke with corrected state, or flag for retry
```

### Sources
- [OpenAI GPT-4.1 Prompting Guide -- tool calling section](https://developers.openai.com/cookbook/examples/gpt4-1_prompting_guide)
- [OpenAI Function Calling Guide](https://developers.openai.com/api/docs/guides/function-calling)
- [Anthropic Tool Use Documentation](https://platform.claude.com/docs/en/docs/build-with-claude/tool-use)
- [LangGraph SQL Agent -- forced tool_choice example](https://docs.langchain.com/oss/python/langgraph/sql-agent)

---

## 5. Negative Constraint Anchoring

### Research Findings: Positive vs Negative Instructions

Multiple studies converge on the same conclusion: **positive instructions outperform negative constraints** for LLMs.

**Token probability mechanics**: LLM token generation inherently selects the next token (positive selection). Negative prompts only slightly reduce probabilities of unwanted tokens, while positive prompts actively amplify desired outcomes. The asymmetry is fundamental to how autoregressive generation works.

**Scaling paradox**: Research from "Beyond Positive Scaling: How Negation Impacts Scaling Trends" shows that larger models actually perform WORSE on negation tasks. The NeQA benchmark demonstrates that negation understanding does not reliably improve as models get larger. GPT-3 and GPT-Neo "consistently struggle with negation across multiple benchmarks" ("Language Models Are Not Naysayers").

### Concrete Rewrites for the Intake Prompt

| Current (Negative) | Rewrite (Positive) |
|---|---|
| "NEVER generate or guess a claim number" | "Claim numbers come only from the submitClaim response. Use the exact number returned." |
| "NEVER do instead: Compute rates yourself" | "All conversions come from the convertCurrency tool. Use its returned rate and amount." |
| "NEVER do instead: Tell the user it's submitted without calling the tool" | "A claim exists in the database only after submitClaim succeeds. Confirm submission using data from the submitClaim response." |
| "Do NOT narrate before tool calls" | "Call tools directly. The UI displays tool activity automatically." |
| "Never show raw error messages to the user" | "Translate errors into conversational language for the user." |

### Optimal Placement and Count

**Where to place negative constraints**: If negative constraints are used, they should appear:
1. Immediately after the positive instruction they guard (not in a separate section)
2. In the final position within the system prompt (models attend more to recency)

**How many is too many**: Research suggests a practical ceiling of **3-5 specific constraints**. Beyond that, conflicting instructions cause the model to spend more attention managing rules than generating quality output. The current prompt has ~10 negative constraints scattered throughout -- this likely dilutes their effectiveness.

**When negatives are appropriate**: Use negative constraints only when a specific, recurring failure mode persists despite clear positive instructions. They work best as targeted patches for observed problems, not as general guardrails.

### The Current Prompt's Constraint Load

The existing prompt contains these negative patterns:
1. "Do NOT narrate before tool calls"
2. "Do NOT output raw JSON"
3. "Do NOT use bracket placeholders"
4. "Never wrap your output in XML tags"
5. "NEVER do instead" (table column, 5 entries)
6. "NEVER generate or guess a claim number"
7. "NEVER use placeholders like '(your employee ID)'"
8. "Never show raw error messages"
9. "Never output bracket placeholders" (repeated)

That is 12+ negative constraints. Based on the research, this should be reduced to 3-5 by converting most to positive instructions and keeping negatives only for the most critical failure modes.

### Sources
- [Gadlet: Why Positive Prompts Outperform Negative Ones](https://gadlet.com/posts/negative-prompting/)
- [VibeSparking: How to Effectively Tell AI What Not to Do](https://www.vibesparking.com/en/blog/ai/prompt-engineering/2025-08-14-prompt-do-not-to-do-playbook/)
- [Beyond Positive Scaling: How Negation Impacts Scaling Trends (NeQA benchmark)](https://arxiv.org/abs/2210.03629)
- [Palantir: Best Practices for LLM Prompt Engineering](https://www.palantir.com/docs/foundry/aip/best-practices-prompt-engineering)
- [Emem Isaac: Prompt Engineering for Agents](https://ememisaac.com/articles/prompt-engineering-for-agents/)

---

## Synthesized Recommendations for the Intake Agent

### Priority 1: Infrastructure Validation (Highest Impact, Addresses Root Cause)

Add post-response validation in `intakeNode` that checks whether the agent claims a submission occurred without `submitClaim` actually being called. This is the only approach that **guarantees** prevention of the CLAIM-1523 class of failure. Prompt changes reduce probability; infrastructure checks eliminate it.

```python
# Pseudocode for intakeNode validation
SUBMISSION_PHRASES = ["submitted successfully", "claim submitted", "has been submitted"]

def detectHallucinatedSubmission(messages):
    submitToolCalled = any(
        hasattr(msg, "name") and msg.name == "submitClaim"
        for msg in messages
    )
    finalResponse = messages[-1].content if hasattr(messages[-1], "content") else ""
    claimsSubmission = any(phrase in finalResponse.lower() for phrase in SUBMISSION_PHRASES)
    
    return claimsSubmission and not submitToolCalled
```

### Priority 2: Restructure Prompt Sections (High Impact)

Reorder the system prompt to follow the evidence-based structure:

```
1. IDENTITY (1 sentence)
2. AGENT PERSISTENCE ("keep going until resolved")
3. TOOL-CALLING DISCIPLINE (the "do NOT guess" mandate)
4. TOOLS REFERENCE (signatures and descriptions)
5. WORKFLOW PHASES (with explicit precondition gates)
6. OUTPUT FORMAT (markdown, no XML)
7. CRITICAL RULES (3-5 max, positive-framed)
8. ERROR HANDLING
```

Move MANDATORY TOOL USAGE up from its current position (section 3 of 8) to position 3 (section 3 of 8, but now after identity/persistence instead of after architecture/output format).

### Priority 3: Replace Negative Constraints with Positive Instructions

Convert the 12+ negative constraints to ~5 positive rules. Keep negative framing only for the most critical failure modes that have actually occurred (like the submission hallucination).

### Priority 4: Add Causal Impossibility Language for submitClaim

Replace the current "NEVER generate or guess a claim number" with causal language:

```
Claim numbers are generated by the database when submitClaim executes.
No claim number exists until the database creates one.
To confirm submission, call submitClaim and use the claim number from its response.
```

### Priority 5: Strengthen Phase Preconditions

Replace the current detection-based phase routing with precondition-based gating:

```
### Phase 3: Submit
PRECONDITIONS (verify ALL before starting):
- A ToolMessage from extractReceiptFields exists in conversation history
- A ToolMessage from searchPolicies exists in conversation history  
- User has explicitly confirmed (said "yes", "confirm", "submit", or equivalent)
- Employee ID is a concrete value you received from the user

If ANY precondition is not met, complete the missing step first.
```

---

## Implementation Context

### What to Change, in What Order

| Order | What | Where | Effort |
|-------|------|-------|--------|
| 1 | Add hallucination detection in intakeNode | `agents/intake/node.py` | Small -- ~20 lines |
| 2 | Restructure prompt section order | `agents/intake/prompts/agentSystemPrompt.py` | Medium -- rewrite |
| 3 | Convert negatives to positives | Same file | Medium -- careful rewrite |
| 4 | Add causal impossibility language | Same file | Small -- targeted edit |
| 5 | Strengthen phase preconditions | Same file | Small -- targeted edit |
| 6 | Add integration test for hallucinated submission | `tests/` | Small -- new test |

### Risk Assessment

- **Infrastructure validation (Priority 1)**: Zero risk. Adds a safety net without changing agent behavior.
- **Prompt restructure (Priority 2-5)**: Medium risk. Changes to system prompts can have unpredictable effects on agent behavior. Must be tested against existing test suite and with manual UAT.
- **Recommended approach**: Ship infrastructure validation first (Priority 1), then iterate on prompt changes with testing after each change.

---

## Sources

### Official Documentation
- [LangGraph create_react_agent](https://docs.langchain.com/oss/python/langgraph) -- API reference and examples
- [LangGraph prebuilt README](https://github.com/langchain-ai/langgraph/blob/main/libs/prebuilt/README.md) -- ReAct agent architecture
- [OpenAI Function Calling Guide](https://developers.openai.com/api/docs/guides/function-calling) -- tool_choice, strict mode, best practices
- [OpenAI GPT-4.1 Prompting Guide](https://developers.openai.com/cookbook/examples/gpt4-1_prompting_guide) -- agentic behavior, tool discipline, section ordering
- [Anthropic Tool Use Documentation](https://platform.claude.com/docs/en/docs/build-with-claude/tool-use) -- tool_choice (auto/any/tool), strict mode
- [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) -- workflow patterns, prompt chaining, gates
- [Anthropic: Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use) -- tool search, programmatic calling, examples
- [Anthropic: Writing Tools for Agents](https://www.anthropic.com/engineering/writing-tools-for-agents) -- tool description best practices

### Research Papers
- [ReAct: Synergizing Reasoning and Acting in Language Models (Yao et al., ICLR 2023)](https://arxiv.org/abs/2210.03629) -- Original ReAct framework
- [Reducing Tool Hallucination via Reliability Alignment (arXiv 2412.04141)](https://arxiv.org/html/2412.04141v1) -- Tool hallucination taxonomy, indecisive actions
- [Tool Receipts: Practical Hallucination Detection for AI Agents (arXiv 2603.10060)](https://arxiv.org/html/2603.10060v1) -- Post-hoc verification of tool calls
- [Internal Representations as Indicators of Hallucinations in Agent Tool Selection (arXiv 2601.05214)](https://arxiv.org/html/2601.05214v1) -- Detecting tool selection errors

### Negative Constraint Research
- [Gadlet: Why Positive Prompts Outperform Negative Ones with LLMs](https://gadlet.com/posts/negative-prompting/) -- Token probability analysis, research citations
- [VibeSparking: Effectively Telling AI What Not to Do](https://www.vibesparking.com/en/blog/ai/prompt-engineering/2025-08-14-prompt-do-not-to-do-playbook/) -- Constraint saturation, rewriting patterns
- [Can Large Language Models Truly Understand Prompts? A Case Study with Negated Prompts](https://arxiv.org/abs/2209.12711) -- InstructGPT negation failures

### Production Agent Patterns
- [AWS: Stop AI Agent Hallucinations: 4 Essential Techniques](https://dev.to/aws/stop-ai-agent-hallucinations-4-essential-techniques-2i94) -- Neurosymbolic guardrails, multi-agent validation
- [Augment Code: 11 Prompting Techniques for Better AI Agents](https://www.augmentcode.com/blog/how-to-build-your-agent-11-prompting-techniques-for-better-ai-agents) -- Context, consistency, tool limitations
- [Emem Isaac: Prompt Engineering for Agents](https://ememisaac.com/articles/prompt-engineering-for-agents/) -- 6-principle framework, production template
- [PromptHub: Prompt Engineering for AI Agents](https://www.prompthub.us/blog/prompt-engineering-for-ai-agents) -- Agent prompt patterns
- [OpenAI Community: Prompting Best Practices for Tool Use](https://community.openai.com/t/prompting-best-practices-for-tool-use-function-calling/1123036) -- Emphasis vs. definition

### LangGraph Issues (Tool Call Failures)
- [LangGraph #720: Tool calls not working](https://github.com/langchain-ai/langgraph/issues/720) -- Agents answering from LLM instead of tools
- [LangChain #36349: Agents silently fail when models forget tool calls](https://github.com/langchain-ai/langchain/issues/36349) -- Silent failures with structured responses
- [LangGraph Discussion #3808: Tools not executing](https://github.com/langchain-ai/langgraph/discussions/3808) -- Null output from tools
