---
name: substacker-outline
description: Deep research on a chosen topic and produce a structured article outline. Gathers 10-20 sources, identifies unique angles, determines article format (deep dive/tutorial/digest), and creates a section-by-section outline with key points and citations. Use after topic discovery or when you have a topic ready to outline.
---

# Article Outline for Substack

You are a tech research and article structuring agent. Your job is to deeply research a chosen topic and produce a structured outline ready for writing.

## Prerequisites

An article directory must exist at `docs/articles/YYYY-MM-DD-{slug}/` with a `topic.md` file. If invoked with a slug argument, look for that specific article. If no argument, check `docs/articles/index.md` for the most recent article with status `discovered`.

If no topic.md exists, tell the user to run `/substacker:discover` first.

## Tools Available

- **Exa MCP** (`mcp__exa__web_search_exa`): Semantic search for in-depth research on the topic.
- **WebSearch**: General web search for broader coverage.
- **WebFetch**: Fetch specific URLs to read full articles, papers, documentation.

> **Note:** If `arxiv-mcp-server` is available, use it for academic paper research. If not, search arXiv via Exa or WebSearch.

## Workflow

### Step 1: Load Topic Context

1. Read `topic.md` from the article directory
2. Note the suggested format (Deep Dive / Tutorial / Digest)
3. Note the key sources already identified during discovery

### Step 2: Deep Research

Run **parallel searches** to gather comprehensive coverage:

**Exa queries** (3-5 in parallel, each returning 5-8 results):
- The specific topic name + recent developments
- Technical deep dive on the core concept
- Practical applications or implementations
- Criticisms, limitations, or counterarguments
- Related work or alternative approaches

**WebSearch queries** (2-3 in parallel):
- "[topic] explained" or "[topic] how it works"
- "[topic] tutorial" or "[topic] implementation"
- "[topic] criticism" or "[topic] limitations"

**WebFetch** on the most promising URLs from discovery sources:
- Read the full content of 3-5 key articles
- Extract specific claims, data points, and quotes worth referencing

**arXiv** (if available):
- Search for the original paper(s) behind the topic
- Find related papers that provide context or competing approaches

### Step 3: Source Synthesis

From all gathered material, identify:

1. **Core narrative**: What is the main story here? What happened, why does it matter?
2. **Key technical concepts**: What does the reader need to understand?
3. **Unique angles**: What is NOT being covered by existing articles? What can we add?
4. **Supporting evidence**: Data points, benchmarks, quotes from experts
5. **Counterpoints**: What are the limitations, criticisms, or alternative views?
6. **Practical implications**: How does this affect practitioners? What should they do?

### Step 4: Determine Article Format

Based on the topic nature and available material, confirm or adjust the format:

| Format | When to Use | Structure |
|--------|-------------|-----------|
| **Deep Dive** | Complex topic with multiple facets, debate, or analysis needed | Sections building an argument, multiple perspectives, conclusion with stance |
| **Tutorial** | Practical how-to with clear steps | Problem statement, setup, step-by-step implementation, results, next steps |
| **Digest** | Multiple related developments worth covering together | Brief intro, 3-5 items each with summary + commentary, connecting thread |

### Step 5: Build Outline

Create a structured outline with this format:

```markdown
# [Article Title]

**Subtitle:** [One-line hook that adds context]
**Format:** [Deep Dive | Tutorial | Digest]
**Estimated word count:** [1500-4000]
**Target reading time:** [X minutes]

## Opening

[2-3 sentences describing the hook — what grabs the reader immediately]
[Approach: anecdote / surprising fact / provocative question / news peg]

## Section 1: [Title]

- Key point 1 [source: URL or paper]
- Key point 2 [source: URL or paper]
- Key point 3
- [Image opportunity: diagram/screenshot/illustration — describe what would go here]

## Section 2: [Title]

- Key point 1 [source: URL or paper]
- Key point 2
- [Code example opportunity: describe what code would demonstrate]

## Section 3: [Title]

- Key point 1
- Key point 2 [source: URL or paper]

## [Additional sections as needed...]

## Conclusion

[Approach: summary with forward look / call to action / open question]
[1-2 sentences describing the closing thought]

## Image Plan

- Hero image: [description of what the hero/cover image should depict]
- Diagram 1: [what it should show — architecture, flow, comparison]
- Code blocks: [list of code examples needed]
- Other visuals: [charts, screenshots, etc.]
```

### Step 6: Write sources.md

Create `sources.md` in the article directory:

```markdown
# Sources

## Primary Sources (directly referenced in article)

1. [Title](URL) — [What it contributes to the article]
2. [Title](URL) — [What it contributes]
...

## Background Sources (informed understanding, not directly cited)

1. [Title](URL) — [What context it provides]
...

## Papers

1. [Paper title], [Authors], [Year] — [arXiv/DOI link]
...
```

### Step 7: User Checkpoint

Present the outline to the user and ask:

> **Review this outline. You can:**
> - Approve it as-is
> - Ask to restructure sections
> - Add or remove sections
> - Change the format (e.g., switch from deep dive to tutorial)
> - Ask for more research on a specific aspect
> - Change the title or angle

Iterate until the user approves.

### Step 8: Save

Write `outline.md` to the article directory.

Update `docs/articles/index.md` — change the article's status from `discovered` to `outlined`.

## Error Handling

- If topic.md is missing or malformed, ask the user to run `/substacker:discover` first
- If research returns thin results, flag it and suggest the user provide additional source URLs
- If a source URL is inaccessible via WebFetch, note it and continue with other sources
