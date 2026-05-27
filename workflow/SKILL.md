---
name: workflow
description: Define and operate reusable development workflow templates for AI agents. Default to the current working directory as the project root, store workflow definitions in `.workflow/definition.json`, and keep runtime state in `.workflow/runtime.json`.
---

# Development Workflow

## Overview

Use this skill when the user asks you to implement a concrete development task such as a feature, bug fix, or refactor. A workflow should break the work into ordered stages with checklist gates so another session can resume cleanly.

## Conceptual Model

| Level | Meaning |
|-------|---------|
| Project | The current repository or directory being worked in. |
| Workflow | A reusable template for a task type. |
| Stage | One ordered step in the workflow. |
| Checklist | Validation items that gate stage completion. |
| Run | The runtime pointer for the active workflow instance. |

## Storage Model

- Store workflow definitions in `[project]/.workflow/definition.json`.
- Store runtime state in `[project]/.workflow/runtime.json`.
- Keep the project root `.gitignore` pointing at `.workflow/runtime.json` so runtime state stays local.
- Resolve the default project from the current working directory when the user does not provide a project path.

## Operating Rules

- Use `move` as the only runtime transition.
- Use `move-stage` and `set-stage-order` only to change the definition order.
- Do not advance until the current stage checklist has been reviewed and satisfied.
- If a task spans sessions, resume from the runtime state rather than recreating the workflow.
- Keep workflow metadata small in `SKILL.md`; put command details and file layout in `references/`.

## Typical Flow

1. Run `create-project` if the directory has not been initialized yet.
2. Create or update the workflow template for the task type.
3. Add stages and checklist items.
4. During work, use `get-current`, `get-checklist`, and `get-next`.
5. Move only after the checklist passes.
6. Reorder stages only when the workflow definition itself changes.

## References

- [usage.md](references/usage.md) for concrete CLI flows
- [commands.md](references/commands.md) for command semantics
- [schema.md](references/schema.md) for the JSON file layout and runtime rules
