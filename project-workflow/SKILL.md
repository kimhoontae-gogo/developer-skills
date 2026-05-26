---
name: project-workflow
description: Manage SQLite-backed project-specific developer workflows with projects, workflows, ordered stages, checklist validation, runtime pointer moves, and cleanup. Use when creating or operating a workflow skill that should resolve the default project from the current working directory unless explicitly overridden.
---

# Project Workflow

## Overview

Use this skill to define and operate developer workflows that live in SQLite rather than markdown. Treat the database as the source of truth for projects, workflow definitions, runtime state, and event history.

## Operating Rules

- Resolve the default project from the current working directory name when the user does not explicitly provide a project name or ID.
- Keep workflow definitions separate from runtime execution state.
- Treat `current`, `checklist`, and `next` as read-oriented operations.
- Treat `move` as the only state transition primitive; moving forward implies the previous stage is considered complete in workflow history.
- Keep stage execution ordered unless the workflow explicitly allows branching.
- Use checklist output to verify that a stage is actually complete before advancing.
- Use `add-stage`, `update-stage`, `remove-stage`, `move-stage`, `set-stage-order`, `update-workflow`, `remove-workflow`, and `remove-project` to manage definitions and cleanup.
- Write workflow `description` so an AI can pick the right workflow for the user's intent without guessing. A good description explains what kind of task the workflow is for (e.g. "Use this for adding new features to a web application", "Use this when debugging production issues").

## Data Layer

- See [usage.md](references/usage.md) for concrete commands and typical flows.
- See [schema.md](references/schema.md) for the SQLite tables, relationships, and state rules.
- See [commands.md](references/commands.md) for the canonical command surface and expected behavior.
- `scripts/workflow_cli.py` is the primary command entry point.
- `scripts/workflow_store.py` contains the SQLite-backed storage layer and CLI implementation.

## Common Commands

- Create a project: `python3 scripts/workflow_cli.py create-project --name "developer-skills"`
- List workflows for a project: `python3 scripts/workflow_cli.py list-workflows --project-name developer-skills`
- Create a workflow with a description: `python3 scripts/workflow_cli.py create-workflow --project-name developer-skills --title "Feature Development" --description "Use this when adding new features to the web application"`
- Update a workflow description: `python3 scripts/workflow_cli.py update-workflow --project-name developer-skills --title "Feature Development" --description "Use this when adding new features or enhancing existing UI/UX"`
- Update a project description: `python3 scripts/workflow_cli.py update-project --project-id 1 --description "QueryPie monorepo"`
- Add a stage: `python3 scripts/workflow_cli.py add-stage --workflow-id 1 --title "Plan" --detail "Define scope"`
- Update a stage: `python3 scripts/workflow_cli.py update-stage --stage-id 1 --title "Planning"`
- Move a stage definition: `python3 scripts/workflow_cli.py move-stage --stage-id 2 --before-stage-id 1`
- Inspect current work: `python3 scripts/workflow_cli.py get-current --project-name developer-skills`
- Inspect checklist: `python3 scripts/workflow_cli.py get-checklist --project-name developer-skills`
- Move runtime pointer: `python3 scripts/workflow_cli.py move --project-name developer-skills --stage-id 2`
- Show workflow status: `python3 scripts/workflow_cli.py status --project-name developer-skills`
- Show event history: `python3 scripts/workflow_cli.py history --project-name developer-skills`

## AI Workflow Selection

When the user asks you to do development work, use `list-workflows` to see what workflows exist and pick the one whose description matches the task:

**Example matching:**
- User says: *"Add OAuth2 login to the API"* → Look for a workflow whose description mentions "feature" or "new functionality".
- User says: *"Fix the SSE reconnect bug"* → Look for a workflow whose description mentions "debug", "bug fix", or "troubleshoot".
- User says: *"Refactor the K8s client initialization"* → Look for a workflow whose description mentions "refactor" or "cleanup".

If no matching workflow exists, create one with a clear description so future sessions can find it.

## Usage Shape

1. Resolve the project from the current working directory.
2. List workflows to find one whose description matches the user's task.
3. If no match exists, create a workflow with a descriptive title and description.
4. Add stages in execution order.
5. Query the current stage and its checklist before claiming completion.
6. Move to the next stage only after validation passes.
