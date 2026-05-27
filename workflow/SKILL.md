---
name: workflow
description: Define and operate reusable development workflow templates (feature development, bug fix, refactoring, etc.) for AI agents. Guides an agent through ordered stages with checklist validation when the user requests a specific unit of development work. Resolves the default project from the current working directory.
---

# Development Workflow

## Overview

Use this skill when the user asks you to **implement a specific development task** — such as adding a feature, fixing a bug, or refactoring code. Instead of jumping straight into implementation, define or follow a structured workflow that breaks the task into ordered stages with validation checklists.

**What this is for:**
- A user says *"Add OAuth2 login to the API"* → Run the **Feature Development** workflow.
- A user says *"Fix the SSE reconnect bug"* → Run the **Bug Fix** workflow.
- A user says *"Refactor the K8s client initialization"* → Run the **Refactoring** workflow.

**What this is NOT for:**
- Long-term project roadmaps or milestone planning. (Use the `plan` skill for that.)
- General project management unrelated to a concrete unit of work.

## Conceptual Model

| Level | Meaning | Example |
|-------|---------|---------|
| **Project** | The git repository you're working in | `hermes-app` |
| **Workflow** | A reusable template for a type of development task | `Feature Development`, `Bug Fix` |
| **Stage** | An ordered step within a workflow | `Understand`, `Design`, `Implement`, `Test`, `Deploy` |
| **Checklist** | Validation items for a stage | `"Write/update unit tests"`, `"Run CI checks"` |
| **Run** | The current execution state of a workflow instance | Which stage the agent is on right now |

Each project can have multiple workflows. The agent picks the appropriate workflow based on the user's request.

## When to Use

- **At the start of a task**: When the user asks you to build/fix/change something, check whether a suitable workflow already exists. If yes, follow it. If no, create one.
- **During execution**: Before claiming a stage is done, inspect its checklist. Only move forward after validation passes.
- **At handoff**: If a task spans multiple sessions, the workflow run state lets the next session resume exactly where you left off.

## Operating Rules

- Resolve the default project from the current working directory name when the user does not explicitly provide a project name or ID.
- **One workflow per task type.** A project can have `Feature Development`, `Bug Fix`, and `Refactoring` workflows side by side.
- The agent executes stages sequentially unless the user explicitly asks to skip or jump.
- `move` is the only runtime state transition. Moving forward implies the previous stage is treated as complete.
- Checklists are gatekeepers. Do not advance until required checklist items are satisfied.
- Stage execution order is fixed unless the workflow definition itself is reordered via `move-stage`.
- Use `set-stage-order` to reorder all active stages at once by listing their IDs in the desired order.

## Typical AI Usage Flow

### Example: Feature Development

```
User: "Add Prometheus metrics to the Hermes API server."

Agent:
1. Look up project = hermes-app (from cwd).
2. Look up workflows for hermes-app.
   → Found: "Feature Development" (id: 3)
3. Check current run state:
   → Not started.
4. Report the upcoming stages and start Stage 1.

[Stage 1: Understand]
- Read existing observability code.
- Verify Prometheus client library is already in go.mod.
- Ask user: "Should this include custom business metrics only, or infra metrics too?"
- Checklist: [✓] Scope clarified

[Stage 2: Design]
- Decide metric names and labels.
- Choose where to register metrics (main.go vs middleware).
- Checklist: [✓] Metric design doc written in PR description

[Stage 3: Implement]
- Write code.
- Checklist: [✓] Code compiles [✓] Unit tests added [✓] Handler updated

[Stage 4: Test]
- Run tests locally.
- Verify `/metrics` endpoint returns expected output.
- Checklist: [✓] Local tests pass [✓] Manual curl check passes

[Stage 5: Deploy / PR]
- Open PR.
- Checklist: [✓] PR description filled [✓] CI passes
```

## Data Layer

- See [usage.md](references/usage.md) for concrete commands and typical flows.
- See [schema.md](references/schema.md) for the SQLite tables, relationships, and state rules.
- See [commands.md](references/commands.md) for the canonical command surface and expected behavior.
- `scripts/workflow_cli.py` is the primary command entry point.
- `scripts/workflow_store.py` contains the SQLite-backed storage layer and CLI implementation.

## Common Commands

```bash
# 1. Ensure the project exists (uses cwd name if omitted)
python3 scripts/workflow_cli.py create-project --name "hermes-app" --description "Hermes Agent console"

# 1b. Refine project metadata when needed
python3 scripts/workflow_cli.py update-project --project-id 1 --description "Hermes Agent console workspace"

# 2. Create a workflow template for this project
python3 scripts/workflow_cli.py create-workflow --project-name hermes-app --title "Feature Development" --description "Standard flow for adding new features"

# 2b. Refine workflow metadata so future sessions can pick it correctly
python3 scripts/workflow_cli.py update-workflow --project-name hermes-app --title "Feature Development" --description "Use this when adding or extending web app features"

# 3. Add stages to the workflow
python3 scripts/workflow_cli.py add-stage --workflow-id 1 --title "Understand" --detail "Read existing code and clarify scope with the user" --checklist '{"item":"Scope is clarified with user","required":true}' --checklist '{"item":"Related files identified","required":true}'
python3 scripts/workflow_cli.py add-stage --workflow-id 1 --title "Implement" --detail "Write code and tests" --checklist '{"item":"Code compiles","required":true}' --checklist '{"item":"Tests pass","required":true}'
python3 scripts/workflow_cli.py add-stage --workflow-id 1 --title "Review & Merge" --detail "Open PR and ensure CI passes" --checklist '{"item":"PR description written","required":true}' --checklist '{"item":"CI is green","required":true}'

# 4. During work, check where you are and what's required
python3 scripts/workflow_cli.py get-current --project-name hermes-app
python3 scripts/workflow_cli.py get-checklist --project-name hermes-app

# 5. Move to the next stage only after validation
python3 scripts/workflow_cli.py move --project-name hermes-app --stage-id 2

# 6. Inspect overall status
python3 scripts/workflow_cli.py status --project-name hermes-app
python3 scripts/workflow_cli.py history --project-name hermes-app

# 7. Reorder all active stages in one shot
python3 scripts/workflow_cli.py set-stage-order --workflow-id 1 --stage-ids 2 3 1
```

## Recommended Workflow Templates

### Feature Development
1. **Understand** — Clarify requirements, identify affected files.
2. **Design** — Decide approach, update API specs if needed.
3. **Implement** — Write backend/frontend code.
4. **Test** — Unit tests, integration tests, manual verification.
5. **Review & Merge** — PR, code review, CI, merge.

### Bug Fix
1. **Reproduce** — Confirm the bug locally.
2. **Root Cause** — Identify the exact line/component causing the issue.
3. **Fix** — Apply minimal fix.
4. **Regression Test** — Add test that fails before fix and passes after.
5. **Verify & Merge** — CI passes, bug is closed.

### Refactoring
1. **Analyze** — Identify targets, measure current state (coverage, complexity).
2. **Plan** — Decide safe refactoring steps.
3. **Execute** — Apply changes incrementally.
4. **Validate** — Tests pass, behavior unchanged.
5. **Clean Up** — Remove dead code, update docs.
