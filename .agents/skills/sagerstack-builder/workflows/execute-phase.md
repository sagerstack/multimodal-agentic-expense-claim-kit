# Workflow: Execute Epic

TODO: Detailed step-by-step workflow for executing a full epic with the builder team.

## Scope

This workflow covers the complete lifecycle of building one epic:

1. **Epic Initialization**: Read all impl plans for the epic, determine story dependency order, validate all required artifacts exist (stories, plans, critical analyses, research)
2. **Team Creation**: Create builder team (`builder-epic-{NNN}`), spawn Software Developer and Code QA agents with full context in spawn prompts
3. **Task List Setup**: Create TaskList items from impl plan parent tasks, set up dependency chains (QA blocked by all impl tasks per story), handle MANUAL task isolation
4. **Story Loop**: For each story in dependency order:
   - Create feature branch (`feature/epic-{NNN}-story-{NNN}`)
   - Merge latest from main
   - Assign SETUP tasks first, then FR/TR/AC tasks sequentially
   - Wait for Developer completion of each task before assigning next
   - After all impl tasks done, assign QA validation
   - Handle QA pass (move to next story) or QA fail (remediation loop, max 2 retries)
5. **Epic Finalization**: Run final full test suite, verify all tasks marked [x], generate epic completion report
6. **Team Shutdown**: Graceful shutdown of all teammates, TeamDelete
7. **Continuation Check**: If --continue flag, check for next epic plans and either auto-chain or prompt for planner

## Key Decision Points

- Story dependency ordering (which story to build first)
- MANUAL task blocking (notify user and wait)
- QA failure handling (remediation vs escalation)
- Continuation mode (single-epic vs auto-chain)

## Error Recovery

- If session crashes mid-epic: Re-invoke builder, resume from TaskList + impl plan [x] markers
- If Developer agent crashes: Re-send task assignment message to wake agent, or spawn replacement after 2 attempts
- If QA agent crashes: Re-assign QA validation task

## References

- SKILL.md workflow_steps section (Steps 1-6)
- references/task-execution.md (completion protocol)
- references/git-workflow.md (branch management)
- references/escalation-protocol.md (when to escalate)
