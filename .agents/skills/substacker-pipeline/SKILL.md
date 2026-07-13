---
name: substacker-pipeline
description: >
  End-to-end Substacker article pipeline with agent team orchestration. Spawns
  a 3-member team (Researcher, Writer, Artist) to discover topics, research,
  outline, write, generate images, and publish articles to Substack. Team Lead
  handles all user checkpoints and Chrome-based publishing. Use when running the
  full article pipeline or resuming an in-progress article.
---

<essential_principles>

## How the Substacker Pipeline Works

These principles ALWAYS apply when orchestrating the article pipeline.

### 1. Sequential Pipeline with User Checkpoints

The pipeline runs 5 stages in strict order. Each stage MUST complete and receive user approval before the next begins.

```
DISCOVER → OUTLINE → WRITE → IMAGES → PUBLISH
   ↓          ↓         ↓        ↓         ↓
 user       user      user     user      user
 picks     approves  approves approves  reviews
 topic     outline    draft    images   in browser
```

### 2. Team Lead Owns All User Interaction

Agents NEVER interact with the user directly. All user-facing communication flows through the Team Lead:
- Agents send results to Team Lead via SendMessage
- Team Lead presents results to user
- Team Lead relays user feedback back to agents
- Team Lead handles all approval/rejection decisions

### 3. Resume Support

Check `docs/articles/index.md` for in-progress articles. Resume from the appropriate stage based on article status:

| Status | Resume From |
|--------|-------------|
| `discovered` | Outline stage |
| `outlined` | Write stage |
| `drafted` | Images stage (or Publish if images exist) |

### 4. Agent Spawn-on-Demand

Spawn agents only when their stage is reached. This avoids idle agents consuming resources during earlier stages.

| Stage | Agent Spawned |
|-------|---------------|
| Discover | Researcher |
| Outline | Researcher (already spawned) |
| Write | Writer |
| Images | Artist |
| Publish | Team Lead handles directly |

### 5. File Ownership

Each agent writes to specific files. No two agents write the same file.

| Agent | Writes | Reads |
|-------|--------|-------|
| Researcher | `topic.md`, `outline.md`, `sources.md` | `index.md` |
| Writer | `draft.md` | `topic.md`, `outline.md`, `sources.md` |
| Artist | `images/*`, `images/prompts.md`, updates `draft.md` image references | `draft.md` |
| Team Lead | `published.md`, `index.md` | All files |

### 6. Article Directory Structure

All article artifacts live under `docs/articles/YYYY-MM-DD-{slug}/`:

```
docs/articles/YYYY-MM-DD-{slug}/
├── topic.md              # From Researcher (discover stage)
├── outline.md            # From Researcher (outline stage)
├── sources.md            # From Researcher (outline stage)
├── draft.md              # From Writer (write stage)
├── images/               # From Artist (images stage)
│   ├── hero.png
│   ├── diagram-*.png
│   ├── code-*.png
│   └── prompts.md
└── published.md          # From Team Lead (publish stage)
```

</essential_principles>

<intake>

## Pipeline Intake

**Step 1: Check for in-progress articles**

Read `docs/articles/index.md`. Look for articles that are NOT `published`.

**Step 2: Present options**

If in-progress articles exist:
```
SUBSTACKER PIPELINE

In-progress articles found:
  - {date} | {slug} | {topic} | {format} | {status}

Options:
  1. Resume "{slug}" from {next stage based on status}
  2. Start a new article

Which would you like?
```

If no in-progress articles (or user chooses new):
```
SUBSTACKER PIPELINE

No in-progress articles. Starting fresh.
```

**Step 3: Determine starting stage**

| Scenario | Starting Stage |
|----------|---------------|
| New article | Discover |
| Resume `discovered` | Outline |
| Resume `outlined` | Write |
| Resume `drafted` (no images/) | Images |
| Resume `drafted` (images/ exists) | Publish |

**Wait for user response before proceeding.**

$ARGUMENTS

</intake>

<team_configuration>

## Substacker Pipeline Team

### Team Identity
- **Team name**: `substacker-{slug}` (e.g., `substacker-2026-02-22-llm-agents`)
- **Description**: "Substacker pipeline: {article topic}"

### Team Members

#### 1. Researcher
- **Subagent type**: `substacker-researcher`
- **Model**: sonnet
- **Permission mode**: bypassPermissions
- **Tools**: Read, Write, Glob, Grep, WebSearch, WebFetch, ToolSearch, SendMessage, TaskUpdate, TaskList
- **Skills preloaded**: `substacker-discover`, `substacker-outline`
- **Max turns**: 80
- **Purpose**: Topic discovery across sources + deep research + structured outline generation

#### 2. Writer
- **Subagent type**: `substacker-writer`
- **Model**: opus
- **Permission mode**: bypassPermissions
- **Tools**: Read, Write, Edit, Glob, Grep, SendMessage, TaskUpdate, TaskList
- **Skills preloaded**: `substacker-write`
- **Max turns**: 80
- **Purpose**: Full article draft with embedded writing style, format-aware structure

#### 3. Artist
- **Subagent type**: `substacker-artist`
- **Model**: sonnet
- **Permission mode**: bypassPermissions
- **Tools**: Read, Write, Bash, Glob, Grep, WebFetch, ToolSearch, SendMessage, TaskUpdate, TaskList
- **Skills preloaded**: `substacker-images`
- **Max turns**: 60
- **Purpose**: Hero images, diagrams, code screenshots, data visualizations

### Spawn Prompt Templates

**Researcher spawn prompt:**
```
You are the Researcher for the Substacker pipeline team working on article "{slug}".

Your skills (substacker-discover, substacker-outline) are preloaded — follow their methodology.

TEAM PROTOCOL:
- You are a teammate, NOT the main session. You cannot interact with the user directly.
- When your skills say "present to user" or "wait for user input," send your output to the Team Lead via SendMessage instead.
- The Team Lead handles all user interaction and will relay feedback to you.
- Mark tasks completed via TaskUpdate when done.
- Article directory: docs/articles/{article-dir}/

Await task assignments from Team Lead.
```

**Writer spawn prompt:**
```
You are the Writer for the Substacker pipeline team working on article "{slug}".

Your skill (substacker-write) is preloaded — follow its methodology and writing style guidelines.

TEAM PROTOCOL:
- You are a teammate, NOT the main session. You cannot interact with the user directly.
- When your skill says "present to user" or "wait for user input," send your output to the Team Lead via SendMessage instead.
- The Team Lead handles all user interaction and will relay feedback to you.
- Mark tasks completed via TaskUpdate when done.
- Article directory: docs/articles/{article-dir}/

Read these files before writing:
- docs/articles/{article-dir}/topic.md
- docs/articles/{article-dir}/outline.md
- docs/articles/{article-dir}/sources.md

Await task assignments from Team Lead.
```

**Artist spawn prompt:**
```
You are the Artist for the Substacker pipeline team working on article "{slug}".

Your skill (substacker-images) is preloaded — follow its methodology.

TEAM PROTOCOL:
- You are a teammate, NOT the main session. You cannot interact with the user directly.
- When your skill says "present to user" or "wait for user input," send your output to the Team Lead via SendMessage instead.
- The Team Lead handles all user interaction and will relay feedback to you.
- Mark tasks completed via TaskUpdate when done.
- Article directory: docs/articles/{article-dir}/

Read the draft before generating images:
- docs/articles/{article-dir}/draft.md

Await task assignments from Team Lead.
```

</team_configuration>

<workflow_steps>

## Pipeline Workflow (8 Steps)

### Step 1: Intake and Resume Check

**Actor**: Team Lead (you)

1. Read `docs/articles/index.md`
2. Check for in-progress articles (status != `published`)
3. Present options to user (see intake section)
4. User selects: resume existing OR start new
5. Determine starting stage and article directory

If starting new, create the article directory:
```
mkdir -p docs/articles/YYYY-MM-DD-{slug}/
```

### Step 2: Create Team and Spawn Researcher

**Actor**: Team Lead

1. Create team:
   ```
   TeamCreate(team_name="substacker-{slug}")
   ```

2. Spawn Researcher:
   ```
   Task(
     subagent_type="substacker-researcher",
     team_name="substacker-{slug}",
     name="researcher",
     prompt="{researcher spawn prompt with article directory}"
   )
   ```

3. Create task list for the pipeline:
   ```
   TaskCreate(subject="Discover trending topic", description="Scan sources, rank topics, write topic.md")
   TaskCreate(subject="Research and outline article", description="Deep research, synthesize sources, write outline.md + sources.md")
   TaskCreate(subject="Write full article draft", description="Draft article from outline, write draft.md")
   TaskCreate(subject="Generate article images", description="Create hero, diagrams, code screenshots, write to images/")
   TaskCreate(subject="Publish to Substack", description="Chrome automation publishing with visual review")
   ```

   Set up dependencies:
   ```
   Task 2 (outline) blocked by Task 1 (discover)
   Task 3 (write) blocked by Task 2 (outline)
   Task 4 (images) blocked by Task 3 (write)
   Task 5 (publish) blocked by Task 4 (images)
   ```

   If resuming, mark completed stages as done and skip their dependencies.

### Step 3: Discover Stage

**Actor**: Team Lead delegates to Researcher

**Skip if**: Resuming from `outlined`, `drafted`, or later.

1. Assign discover task to Researcher:
   ```
   TaskUpdate(discoverTaskId, owner="researcher", status="in_progress")
   SendMessage(
     type="message",
     recipient="researcher",
     content="TASK: Discover trending topic

     Follow your substacker-discover skill methodology:
     1. Scan sources in parallel (Exa, WebSearch, arXiv, HN)
     2. Cross-reference and score topics
     3. Rank 3-5 topics

     Send me your ranked topic list with:
     - Topic title
     - Why it's trending
     - Suggested format (Deep Dive / Tutorial / Digest)
     - Key sources found
     - Unique angle

     Write topic.md AFTER I confirm the user's choice.
     Article directory: docs/articles/{article-dir}/",
     summary="Discover trending AI/ML topic"
   )
   ```

2. Wait for Researcher to send ranked topics

3. Present topics to user:
   ```
   TOPIC DISCOVERY RESULTS

   The Researcher found these trending topics:

   1. {topic 1} — {why trending}
      Format: {suggested} | Sources: {count}
      Angle: {unique angle}

   2. {topic 2} — ...

   3. {topic 3} — ...

   Pick a topic (1-N), modify one, or supply your own topic.
   ```

4. Relay user's choice to Researcher:
   ```
   SendMessage(
     type="message",
     recipient="researcher",
     content="USER SELECTED: {topic details}. Write topic.md to docs/articles/{article-dir}/topic.md and update docs/articles/index.md with status 'discovered'.",
     summary="User selected topic"
   )
   ```

5. Wait for Researcher confirmation, mark discover task complete

### Step 4: Outline Stage

**Actor**: Team Lead delegates to Researcher

**Skip if**: Resuming from `outlined`, `drafted`, or later.

1. Assign outline task to Researcher:
   ```
   TaskUpdate(outlineTaskId, owner="researcher", status="in_progress")
   SendMessage(
     type="message",
     recipient="researcher",
     content="TASK: Research and outline article

     Follow your substacker-outline skill methodology:
     1. Read topic.md for context
     2. Deep research: gather 10-20 sources via parallel queries
     3. Synthesize: identify core narrative, unique angles, counterpoints
     4. Determine format (Deep Dive / Tutorial / Digest)
     5. Build structured outline with sections, key points, citations
     6. Write sources.md and outline.md

     Send me:
     - The complete outline (title, subtitle, section headers with bullet points)
     - Source count and quality assessment
     - Recommended format with reasoning
     - Image plan (where images should go)

     Article directory: docs/articles/{article-dir}/",
     summary="Research and outline article"
   )
   ```

2. Wait for Researcher to send outline

3. Present outline to user:
   ```
   ARTICLE OUTLINE

   Title: {title}
   Subtitle: {subtitle}
   Format: {format} | Sources: {count}

   {Full outline with section headers and bullet points}

   IMAGE PLAN:
   {Where images are planned}

   Approve this outline, request changes, or restructure?
   ```

4. If user requests changes:
   ```
   SendMessage(
     type="message",
     recipient="researcher",
     content="USER FEEDBACK: {changes requested}. Revise outline.md and send updated version.",
     summary="Outline revision requested"
   )
   ```
   Loop until user approves.

5. After approval, confirm Researcher has written `outline.md` + `sources.md` and updated index to `outlined`

6. Mark outline task complete

### Step 5: Write Stage

**Actor**: Team Lead delegates to Writer

**Skip if**: Resuming from `drafted` or later.

1. Spawn Writer (on-demand):
   ```
   Task(
     subagent_type="substacker-writer",
     team_name="substacker-{slug}",
     name="writer",
     prompt="{writer spawn prompt with article directory}"
   )
   ```

2. Assign write task:
   ```
   TaskUpdate(writeTaskId, owner="writer", status="in_progress")
   SendMessage(
     type="message",
     recipient="writer",
     content="TASK: Write full article draft

     Follow your substacker-write skill methodology:
     1. Read outline.md, sources.md, topic.md
     2. Write full article following the outline structure
     3. Apply writing style guidelines from your skill
     4. Mark image placements with <!-- IMAGE: type - description --> comments
     5. Self-review against the style checklist
     6. Write draft.md

     Send me the complete draft for user review.
     Article directory: docs/articles/{article-dir}/",
     summary="Write article draft"
   )
   ```

3. Wait for Writer to send draft

4. Present draft to user:
   ```
   ARTICLE DRAFT

   Title: {title}
   Word count: {count} | Format: {format}

   {Full draft content}

   ---
   IMAGE MARKERS: {count} images planned
   ---

   Approve this draft, request edits, or rewrite specific sections?
   ```

5. If user requests edits:
   ```
   SendMessage(
     type="message",
     recipient="writer",
     content="USER FEEDBACK: {edits requested}. Update draft.md and send revised version.",
     summary="Draft revision requested"
   )
   ```
   Loop until user approves.

6. After approval, confirm Writer has written `draft.md` and updated index to `drafted`

7. Mark write task complete

### Step 6: Images Stage

**Actor**: Team Lead delegates to Artist

**Skip if**: Resuming with existing `images/` directory (user can choose to regenerate).

1. Spawn Artist (on-demand):
   ```
   Task(
     subagent_type="substacker-artist",
     team_name="substacker-{slug}",
     name="artist",
     prompt="{artist spawn prompt with article directory}"
   )
   ```

2. Assign images task:
   ```
   TaskUpdate(imagesTaskId, owner="artist", status="in_progress")
   SendMessage(
     type="message",
     recipient="artist",
     content="TASK: Generate article images

     Follow your substacker-images skill methodology:
     1. Scan draft.md for <!-- IMAGE: type - description --> markers
     2. Generate each image by type (hero, diagram, code, chart)
     3. Save to images/ directory
     4. Record prompts in images/prompts.md
     5. Update draft.md to replace markers with ![alt](images/filename.png)

     Send me a summary of all generated images with:
     - Filename and type
     - Generation method used
     - Any failures or fallbacks applied

     Article directory: docs/articles/{article-dir}/",
     summary="Generate article images"
   )
   ```

3. Wait for Artist to send results

4. Present images to user:
   ```
   ARTICLE IMAGES

   Generated {count} images:

   1. {filename} — {type} — {method}
   2. {filename} — {type} — {method}
   ...

   The images are saved to docs/articles/{article-dir}/images/
   Review them and let me know:
   - Approve all
   - Regenerate specific images
   - Skip any images
   ```

5. If user requests regeneration:
   ```
   SendMessage(
     type="message",
     recipient="artist",
     content="USER FEEDBACK: Regenerate {specific images}. {Additional guidance}.",
     summary="Image regeneration requested"
   )
   ```
   Loop until user approves.

6. Mark images task complete

### Step 7: Publish Stage

**Actor**: Team Lead handles directly

This stage uses Chrome browser automation. The Team Lead executes publishing because:
- Chrome MCP tools require visual user confirmation
- Publishing is irreversible — needs direct user oversight
- Browser state management is session-specific

1. Load article content:
   - Read `docs/articles/{article-dir}/draft.md` for title, subtitle, body
   - Scan `docs/articles/{article-dir}/images/` for image files

2. Check browser state:
   ```
   ToolSearch: "chrome tabs"
   mcp__claude-in-chrome__tabs_context_mcp → check current tabs
   ```

3. Verify Substack login:
   - Navigate to Substack dashboard
   - If not logged in: ask user to log in manually, wait for confirmation

4. Navigate to Substack post editor:
   ```
   mcp__claude-in-chrome__navigate → https://{publication}.substack.com/publish/post
   ```

5. Fill post content section by section:
   - Title
   - Subtitle
   - Body (paste in sections to avoid truncation)
   - Upload images

6. Set metadata:
   - Tags/topics
   - Preview text
   - SEO title

7. **MANDATORY VISUAL REVIEW CHECKPOINT**:
   ```
   PUBLISH REVIEW

   The article is loaded in Substack's editor. Please review it in your browser:

   - Title and subtitle correct?
   - Body formatting looks right?
   - Images display properly?
   - Tags and metadata set?

   Options:
   1. Publish now
   2. Schedule for later (specify date/time)
   3. Save as draft (don't publish yet)
   4. Something needs fixing (describe what)
   ```

   **NEVER auto-publish.** Wait for explicit user approval.

8. Execute user's choice:
   - Publish: Click publish button, capture URL
   - Schedule: Set schedule, confirm
   - Draft: Save, note draft status

9. Write `published.md`:
   ```markdown
   # Published: {title}

   - **URL**: {substack URL}
   - **Published**: {date and time}
   - **Format**: {format}
   - **Tags**: {tags}
   - **Status**: {published/scheduled/draft}
   ```

10. Update `docs/articles/index.md` status to `published`

11. Mark publish task complete

**Fallback**: If Chrome automation fails at any point:
- Stop and inform user
- Provide copy-paste-ready content (title, subtitle, body as formatted markdown)
- Provide image files location for manual upload
- Still write `published.md` with `status: manual` and update index

### Step 8: Team Shutdown

**Actor**: Team Lead

1. Shut down all active agents:
   ```
   SendMessage(type="shutdown_request", recipient="researcher", content="Pipeline complete. Shutting down.")
   SendMessage(type="shutdown_request", recipient="writer", content="Pipeline complete. Shutting down.")
   SendMessage(type="shutdown_request", recipient="artist", content="Pipeline complete. Shutting down.")
   ```

   Only send to agents that were spawned (skip if agent was never needed due to resume).

2. Wait for shutdown confirmations

3. Delete team:
   ```
   TeamDelete
   ```

4. Present completion summary:
   ```
   PIPELINE COMPLETE

   Article: {title}
   Slug: {slug}
   URL: {substack URL or "saved as draft"}

   Artifacts:
   - docs/articles/{article-dir}/topic.md
   - docs/articles/{article-dir}/outline.md
   - docs/articles/{article-dir}/sources.md
   - docs/articles/{article-dir}/draft.md
   - docs/articles/{article-dir}/images/ ({count} images)
   - docs/articles/{article-dir}/published.md

   Index updated: docs/articles/index.md
   ```

</workflow_steps>

<error_handling>

## Error Handling

### Agent Failures

If an agent stops responding or errors out:
1. Check task status via TaskList
2. If agent crashed mid-task, read partially written files
3. Inform user: "The {role} agent encountered an issue at {stage}. Partially completed work is saved."
4. Offer options: retry stage with new agent spawn, or continue manually

### Chrome Automation Failures

If Chrome MCP tools fail during publishing:
1. Stop immediately — do not retry Chrome actions blindly
2. Inform user of the specific failure
3. Fall back to manual publishing mode:
   - Output formatted content for copy-paste
   - List image files for manual upload
4. Still complete the pipeline (mark as manual publish)

### MCP Server Unavailable

If an MCP server (Exa, arxiv, image-gen, mermaid) is not available:
1. Agent should use fallback tools (WebSearch instead of Exa, Bash CLI instead of MCP)
2. If no fallback available, agent reports to Team Lead
3. Team Lead informs user and asks how to proceed

### Iteration Limits

- Topic discovery: max 2 rounds of "show more topics" before user must pick or supply own
- Outline revision: max 3 revision cycles
- Draft revision: max 3 revision cycles
- Image regeneration: max 2 rounds per image

After limits reached, proceed with current version and note in pipeline summary.

</error_handling>

<verification>

## Post-Pipeline Checklist

After the pipeline completes, verify:

### Artifacts
- [ ] `docs/articles/{article-dir}/topic.md` exists
- [ ] `docs/articles/{article-dir}/outline.md` exists
- [ ] `docs/articles/{article-dir}/sources.md` exists
- [ ] `docs/articles/{article-dir}/draft.md` exists
- [ ] `docs/articles/{article-dir}/images/` directory with generated images
- [ ] `docs/articles/{article-dir}/images/prompts.md` exists
- [ ] `docs/articles/{article-dir}/published.md` exists

### Index
- [ ] `docs/articles/index.md` has entry with status `published`

### Quality
- [ ] Article follows writing style guidelines
- [ ] All image markers in draft replaced with actual image references
- [ ] Sources cited inline as hyperlinks
- [ ] Article published (or saved as draft) on Substack

### Team
- [ ] All agents shut down
- [ ] Team deleted

</verification>
