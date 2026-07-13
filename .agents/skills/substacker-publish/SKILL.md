---
name: substacker-publish
description: Publish a completed article to Substack using Chrome browser automation. Opens Substack, creates a new post, pastes content with images, and waits for visual review before publishing. Use after draft and images are finalized.
---

# Publish to Substack via Chrome

You are a publishing agent. Your job is to take a completed article draft and publish it to Substack using Chrome browser automation.

## Prerequisites

An article directory must exist at `docs/articles/YYYY-MM-DD-{slug}/` with a `draft.md` file. If invoked with a slug argument, look for that specific article. If no argument, check `docs/articles/index.md` for the most recent article with status `drafted`.

If draft.md is missing, tell the user to run `/substacker:write` first.

## Tools Available

- **`mcp__claude-in-chrome__tabs_context_mcp`**: Get current browser tab state
- **`mcp__claude-in-chrome__navigate`**: Navigate to a URL
- **`mcp__claude-in-chrome__read_page`**: Read page content
- **`mcp__claude-in-chrome__form_input`**: Fill form fields
- **`mcp__claude-in-chrome__computer`**: Click, type, scroll, and other interactions
- **`mcp__claude-in-chrome__javascript_tool`**: Execute JavaScript on the page
- **`mcp__claude-in-chrome__find`**: Find elements on page
- **`mcp__claude-in-chrome__upload_image`**: Upload image files
- **`mcp__claude-in-chrome__get_page_text`**: Get all text from page

## Important Warnings

- **NEVER auto-publish without user confirmation.** Always pause for visual review.
- **NEVER trigger JavaScript alerts or confirm dialogs.** These block the extension.
- **Be patient with page loads.** Substack's editor can be slow. Wait for elements to appear.
- If Chrome automation breaks mid-flow, stop and tell the user to complete manually.

## Workflow

### Step 1: Load Article Content

1. Read `draft.md` — the full article to publish
2. Read `topic.md` — for title, subtitle, tags
3. Check if `images/` directory exists with generated images
4. Parse the draft for:
   - Title (first `#` heading)
   - Subtitle (if present, the line after the title)
   - Full body content
   - Image references (`![alt](images/filename.png)`)

### Step 2: Check Browser State

1. Call `tabs_context_mcp` to see current browser tabs
2. Check if user is already logged into Substack
3. If not logged in, tell the user: "Please log into your Substack account in Chrome, then tell me to continue."

### Step 3: Navigate to Substack Editor

1. Navigate to the Substack new post page (typically `https://[publication].substack.com/publish/post`)
2. Wait for the editor to load
3. Verify the editor is ready by checking for the title input field

If the exact URL is unknown, ask the user for their Substack publication URL.

### Step 4: Fill Post Content

Proceed carefully, one step at a time:

1. **Title**: Find the title input field and enter the article title
2. **Subtitle**: If the editor has a subtitle field, enter the subtitle
3. **Body content**:
   - The Substack editor uses a rich text editor
   - Paste the article content section by section
   - For each section: find the editor area, type/paste the content
   - Handle markdown formatting (headers, bold, links, code blocks)
4. **Images**:
   - For each image reference in the draft, use `upload_image` to upload from the local `images/` directory
   - Place images at the correct positions in the article

> **Important**: Substack's editor may not accept raw markdown. You may need to:
> - Use keyboard shortcuts for formatting (Cmd+B for bold, etc.)
> - Paste plain text and apply formatting
> - Use the editor's built-in tools for headers, links, code blocks

### Step 5: Set Post Metadata

If the editor exposes these settings:

1. **Tags/Topics**: Add relevant tags based on the topic
2. **Preview text**: Use the first 1-2 sentences of the article
3. **SEO title**: Use the article title (or a shorter version)

### Step 6: Visual Review Checkpoint

**This is mandatory. Do NOT skip.**

Tell the user:

> **The article is loaded in Substack's editor. Please review it in your browser:**
>
> - Check that formatting looks correct
> - Verify images are properly placed
> - Review the title and subtitle
> - Check any links are working
>
> **When ready, tell me to:**
> - **"Publish"** — I'll click the publish button
> - **"Schedule for [date/time]"** — I'll set the schedule
> - **"Save as draft"** — I'll save without publishing
> - **"Fix [issue]"** — I'll try to fix specific formatting issues

Wait for the user's explicit instruction before proceeding.

### Step 7: Publish or Schedule

Based on user instruction:

- **Publish now**: Click the publish/send button
- **Schedule**: Set the date/time, then confirm the schedule
- **Save draft**: Ensure the draft is saved (usually auto-saved, but verify)

### Step 8: Capture and Record

After publishing:

1. Wait for the published page to load
2. Capture the published URL from the browser
3. Write `published.md` to the article directory:

```markdown
# Published

**URL:** [published URL]
**Published:** YYYY-MM-DD HH:MM
**Status:** published | scheduled | draft
**Tags:** [list of tags applied]

## Post-Publish Notes

[Any notes about the publishing process — issues encountered, manual fixes needed, etc.]
```

4. Update `docs/articles/index.md` — change status to `published`.

## Fallback: Manual Publishing

If Chrome automation encounters issues at any point:

1. **Stop immediately** — don't try to force through browser issues
2. Tell the user exactly what happened
3. Provide the draft content in a format ready for manual copy-paste:
   - Plain text version of the article
   - List of images to upload manually
   - Suggested tags and metadata
4. Update `published.md` with status `manual` and notes about what went wrong

## Error Handling

- **Login required**: Ask user to log in manually, then retry
- **Editor not loading**: Wait longer, retry once, then fall back to manual
- **Image upload fails**: Skip that image, note it for manual upload
- **Formatting issues**: Flag for user review during the visual checkpoint
- **Publish button not found**: Fall back to manual publishing
- **Browser extension not responding**: Stop and inform user
