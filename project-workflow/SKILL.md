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
- Use `add-stage`, `update-stage`, `remove-stage`, `move-stage`, `remove-workflow`, and `remove-project` to manage definitions and cleanup.

## Data Layer

- See [usage.md](references/usage.md) for concrete commands and typical flows.
- See [schema.md](references/schema.md) for the SQLite tables, relationships, and state rules.
- See [commands.md](references/commands.md) for the canonical command surface and expected behavior.
- `scripts/workflow_cli.py` is the primary command entry point.
- `scripts/workflow_store.py` contains the SQLite-backed storage layer and CLI implementation.

## Common Commands

- Create a project: `python3 scripts/workflow_cli.py create-project --name "developer-skills"`
- Create a workflow: `python3 scripts/workflow_cli.py create-workflow --project-name developer-skills --title "Web App"`
- Add a stage: `python3 scripts/workflow_cli.py add-stage --workflow-id 1 --title "Plan" --detail "Define scope"`
- Update a stage: `python3 scripts/workflow_cli.py update-stage --stage-id 1 --title "Planning"`
- Move a stage definition: `python3 scripts/workflow_cli.py move-stage --stage-id 2 --before-stage-id 1`
- Inspect current work: `python3 scripts/workflow_cli.py get-current --project-name developer-skills`
- Inspect checklist: `python3 scripts/workflow_cli.py get-checklist --project-name developer-skills`
- Move runtime pointer: `python3 scripts/workflow_cli.py move --project-name developer-skills --stage-id 2`
- Show workflow status: `python3 scripts/workflow_cli.py status --project-name developer-skills`
- Show event history: `python3 scripts/workflow_cli.py history --project-name developer-skills`

## Usage Shape

- Start from a project.
- Attach one or more workflows to that project.
- Query the current stage and its checklist before claiming completion.
- Move to the next stage only after validation passes.
