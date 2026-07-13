# Workflow: Execute Story

TODO: Detailed step-by-step workflow for executing a single story within an epic.

## Scope

This workflow covers building one specific story without full epic orchestration. Used when:
- User wants to implement a single story from an already-planned epic
- Resuming work on a partially-completed story
- Re-implementing a story after significant changes to its impl plan

## Steps

1. **Story Selection**: Validate the story exists, read its impl plan, user story, and any tech research
2. **Environment Check**: Verify branch exists or create it, merge latest from main, check local dev environment
3. **Team Creation**: Create builder team scoped to one story, spawn Developer and QA
4. **Task Creation**: Create TaskList items from the story's impl plan parent tasks only (not other stories)
5. **Implementation**: Assign tasks to Developer sequentially (SETUP -> FR -> TR -> AC -> DOC)
6. **QA Gate**: Assign QA validation after all impl tasks complete
7. **Remediation**: If QA fails, create targeted remediation tasks (max 2 retries)
8. **Completion**: Mark story complete, update project memory, report to user
9. **Team Shutdown**: Graceful shutdown, TeamDelete

## Differences from Execute Epic

- Only one story, not all stories in the epic
- Single feature branch, no branch switching
- No continuation mode (single story only)
- Team name: `builder-story-{NNN}-epic-{NNN}` (instead of `builder-epic-{NNN}`)

## References

- SKILL.md workflow_steps Step 4 (Story Execution Loop)
- references/task-execution.md
- references/git-workflow.md
