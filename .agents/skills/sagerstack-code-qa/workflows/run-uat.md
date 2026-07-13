# Workflow: Run UAT

## Purpose

UAT-only validation workflow for when the Team Lead requests targeted UAT execution (e.g., after infrastructure fixes or Docker configuration changes).

## TODO: Implementation Details

This workflow will contain the step-by-step execution guide for UAT-only validation:

1. **Detection Phase**
   - Check for docker-compose.yml/yaml in project root
   - Check for application entry point if no docker-compose
   - Determine UAT execution model (Docker / local process / skip)

2. **Environment Preparation**
   - Verify Docker daemon running (if Docker UAT)
   - Verify .env.local exists (if integration services needed)
   - Check port availability

3. **Application Startup**
   - Docker: `docker-compose up -d --build` with health check wait
   - Local: Start process in background with startup wait
   - Timeout handling (30s for Docker, 10s for local)

4. **E2E Scenario Execution**
   - Parse E2E ACs from user story
   - Execute HTTP assertions per scenario (see references/uat-patterns.md)
   - Record status codes, response bodies, timing

5. **Evidence Capture**
   - Save docker-compose logs on failure
   - Capture full curl output for failed scenarios
   - Record timing information

6. **Cleanup**
   - Docker: `docker-compose down`
   - Local: Kill process, verify port freed

7. **Report**
   - Generate UAT Results section of QA report
   - Send results to Team Lead
