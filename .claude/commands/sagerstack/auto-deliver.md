Invoke the `auto-delivery` skill.

This spawns a 2-member agent team (Developer + QA) to autonomously deliver phases. Developer implements GSD plans directly using sagerstack skills (TDD, Docker-first, 90% coverage). QA validates with 9-check quality pipeline + Playwright browser UAT. Team Lead provides progressive updates and manages GSD state.

Fully autonomous — only stops for escalation (3 failed fix cycles) or final completion.

User input: $ARGUMENTS

Accepts one of two flags:
- `--milestone <version>` (e.g., `--milestone 2.0`) — deliver ALL phases in that milestone, in roadmap order
- `--phase <number>` (e.g., `--phase 6`) — deliver a single phase only

If neither flag is provided, deliver all remaining phases in the active milestone.
