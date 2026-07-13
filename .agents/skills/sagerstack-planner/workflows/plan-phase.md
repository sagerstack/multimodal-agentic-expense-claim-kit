# Plan Epic Workflow

TODO: Full 9-step planning workflow for a single epic.

## Purpose
Orchestrates the complete planning workflow for one epic from project-context.md.
This is the primary workflow invoked when a user selects an epic to plan.

## Steps Covered
1. Read epic context and create team
2. Delegate research to Researcher
3. Delegate proposal generation to BA
4. Present proposals to user (Q&A Point 1)
5. Delegate full story generation to BA, present to user (Q&A Point 2)
6. Delegate technical Q&A to Solution Architect, present to user (Q&A Point 3)
7. Delegate implementation plan generation to Solution Architect
8. Delegate critical review to Critical Analyst (max 2 refinement cycles)
9. Verify artifacts, present summary, shut down team

## Key Behaviors
- Team Lead coordinates all communication between agents and user
- Agents communicate through Team Lead (not directly with user)
- User Q&A gates at steps 4, 5, and 6
- Refinement loop between Architect and Critic at step 8
- All artifacts saved to docs/phases/epic-{NNN}-{desc}/

## References
- SKILL.md <workflow_steps> section for detailed step definitions
- SKILL.md <team_configuration> for agent capabilities
- SKILL.md <artifact_templates> for output formats
