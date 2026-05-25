# SQLite Schema

## Goals

- Store development workflow definitions in SQLite.
- Keep runtime state separate from definitions.
- Support resuming a development task from the current stage or jumping to a chosen stage.
- Preserve enough history to explain why a workflow advanced.

## Tables

### `projects`

Top-level container. A project groups workflows for one git repository.

Suggested columns:
- `id`
- `name`
- `description`
- `created_at`
- `updated_at`

### `workflows`

Workflow definition for a project. Each workflow represents a reusable development task template (e.g., "Feature Development", "Bug Fix").

Suggested columns:
- `id`
- `project_id`
- `title`
- `description`
- `status`
- `created_at`
- `updated_at`

### `workflow_stages`

Ordered stage definitions for one workflow.

Suggested columns:
- `id`
- `workflow_id`
- `position`
- `title`
- `detail`
- `status`
- `created_at`
- `updated_at`

Stage status should describe the definition lifecycle only when needed. Runtime progress belongs elsewhere.

### `stage_checklists`

Checklist items used to validate whether the active stage is complete.

Suggested columns:
- `id`
- `stage_id`
- `position`
- `item`
- `required`
- `created_at`
- `updated_at`

### `workflow_runs`

Runtime state for a workflow instance.

Suggested columns:
- `id`
- `workflow_id`
- `current_stage_id`
- `status`
- `started_at`
- `updated_at`
- `completed_at`

### `workflow_events`

Append-only audit trail.

Suggested columns:
- `id`
- `entity_type`
- `entity_id`
- `event_type`
- `payload_json`
- `created_at`

## Default Project Resolution

- Use the current working directory name as the default project key.
- Override only when the user explicitly supplies a project name or ID.
- Keep this resolution rule in the command layer so all commands behave consistently.

## Invariants

- One workflow run should have one current stage at a time.
- Stage order should be stable and deterministic.
- Checklist validation should read from the active stage only.
- A move operation should update the runtime pointer and emit an event.
- Advancing to the next stage does not require a separate per-stage completion record; the new pointer position is the proof of progress.
- Definitions should not overwrite runtime progress.
