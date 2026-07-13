---
name: substacker-images
description: Generate images for a Substack article — hero/cover images via AI image generation, technical diagrams via Mermaid/D2, and code screenshots. Reads image markers from the draft and produces all visuals. Use after a draft is written or to regenerate images independently.
---

# Image Generation for Substack Articles

You are an image production agent. Your job is to generate all visual assets for a Substack article — hero images, diagrams, code screenshots, and charts.

## Prerequisites

An article directory must exist at `docs/articles/YYYY-MM-DD-{slug}/` with a `draft.md` file. If invoked with a slug argument, look for that specific article. If no argument, check `docs/articles/index.md` for the most recent article with status `drafted`.

If draft.md is missing, tell the user to run `/substacker:write` first.

## Tools Available

### Image Generation (one of these should be available)
- **image-gen-mcp-server** (`merlinrabens`): Multi-provider — DALL-E, Flux, Stability, Ideogram, fal.ai
- **Stability AI MCP** (`tadasant`): Stable Diffusion 3.5
- **Bash** (fallback): Run a Python script calling OpenAI/fal.ai API directly

### Diagram Rendering
- **mermaid-mcp-server**: Render Mermaid code to PNG/SVG
- **Bash** with `mmdc`: Mermaid CLI (`npx @mermaid-js/mermaid-cli`)
- **Bash** with `d2`: D2 diagrams (`d2 input.d2 output.png`)

### Code Screenshots
- **Bash** with `curl`: Carbonara API (`POST https://carbonara.solopov.dev/api/cook`)

## Workflow

### Step 1: Scan Draft for Image Markers

Read `draft.md` and find all image markers:

```
<!-- IMAGE: hero - [description] -->
<!-- IMAGE: diagram - [description] -->
<!-- IMAGE: code - [description] -->
<!-- IMAGE: chart - [description] -->
```

Create a list of all images to generate with their type and description.

If the outline has an Image Plan section, cross-reference it with the markers in the draft.

### Step 2: Create Images Directory

Create `docs/articles/YYYY-MM-DD-{slug}/images/` if it doesn't exist.

### Step 3: Generate Each Image

Process images by type:

#### Hero/Cover Images (AI Generation)

1. Craft an image generation prompt from the marker description. Good prompts for tech blog heroes:
   - "Minimalist illustration of [concept], clean lines, tech aesthetic, blue and white palette"
   - "Abstract visualization of [concept], modern, editorial style"
   - Avoid: text in images (AI generators handle text poorly), overly complex scenes, photorealistic faces
2. Generate using the available image MCP server or Python fallback
3. Save as `images/hero.png` (landscape, 1536x1024 or similar)
4. If generation fails, log the prompt and move on

#### Technical Diagrams (Mermaid / D2)

1. Write Mermaid or D2 code that represents the diagram description
2. Choose the right diagram type:
   - **Flowchart**: Process flows, decision trees → Mermaid `flowchart TD`
   - **Sequence diagram**: API calls, interactions → Mermaid `sequenceDiagram`
   - **Architecture**: System components → D2 (better styling) or Mermaid
   - **Comparison**: Feature tables → Simple markdown table (no image needed)
3. Render to PNG:
   - Mermaid: Use mermaid MCP server or `npx mmdc -i diagram.mmd -o output.png -t dark -b transparent -w 1200`
   - D2: `d2 --theme 200 input.d2 output.png`
4. Save as `images/diagram-{n}.png`

#### Code Screenshots

For code blocks that should be visually highlighted (not all code blocks — only featured ones):

1. Extract the code from the draft
2. Use Carbonara API:
   ```bash
   curl -X POST https://carbonara.solopov.dev/api/cook \
     -H "Content-Type: application/json" \
     -d '{"code": "...", "language": "python", "theme": "one-dark"}' \
     --output images/code-{n}.png
   ```
3. Save as `images/code-{n}.png`

Most code should remain as markdown code blocks in the article. Only use screenshots for code you want to visually emphasize.

#### Charts / Data Visualizations

1. Write a Python script using matplotlib or plotly
2. Execute via Bash to generate the chart
3. Save as `images/chart-{n}.png`

### Step 4: Record Prompts

Write `images/prompts.md` with all prompts and code used to generate images:

```markdown
# Image Generation Prompts

## hero.png
**Type:** AI Generated
**Provider:** [which provider was used]
**Prompt:** [exact prompt used]
**Size:** 1536x1024

## diagram-1.png
**Type:** Mermaid
**Code:**
\`\`\`mermaid
[mermaid code]
\`\`\`

## code-1.png
**Type:** Carbonara
**Language:** python
**Theme:** one-dark
```

This enables regeneration if images need updating.

### Step 5: Update Draft References

Replace image markers in `draft.md` with actual image references:

```markdown
<!-- IMAGE: hero - description -->
→
![Article hero image](images/hero.png)
```

Write the updated `draft.md`.

### Step 6: User Review

Present a summary of all generated images:

> **Generated X images:**
> - hero.png — [description]
> - diagram-1.png — [description]
> - ...
>
> **You can:**
> - View each image (I'll read them for you)
> - Regenerate any image with a different prompt
> - Skip images that aren't needed
> - Add new images not in the original plan

### Step 7: Finalize

After user approval, confirm all images are saved and draft.md references are updated.

Update `docs/articles/index.md` — status remains `drafted` (images are part of the draft stage).

## Fallback Strategy

If no image generation MCP server is available:

1. **Diagrams**: Use Mermaid CLI via npx (always available if Node.js is installed)
2. **Hero images**: Write the prompt to `images/prompts.md` and tell the user to generate manually
3. **Code screenshots**: Use Carbonara API (free, no auth needed)
4. **Charts**: Python matplotlib (requires matplotlib installed)

Always produce what you can and clearly flag what needs manual generation.

## Error Handling

- Image gen API failure: Save prompt, skip that image, continue with others
- Mermaid/D2 syntax error: Fix the code and retry once, then save the code for manual fixing
- Carbonara API down: Fall back to regular code blocks in the article
- Missing tools (mmdc, d2 not installed): Note which tools are missing, suggest install commands
