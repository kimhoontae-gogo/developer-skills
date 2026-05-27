# JSON Schema

## Goals

- Store workflow definitions in a project-local JSON file.
- Keep runtime state separate from definitions.
- Make definition changes trackable in git while runtime state stays local.
- Support resuming from the current stage or jumping to a chosen stage.

## File Layout

### `definition.json`

Tracked source of truth for the project workflow definition.

Suggested structure:

```json
{
  "schema_version": 1,
  "project": {
    "name": "hermes-app",
    "description": "Hermes Agent console",
    "created_at": "2026-05-28T12:00:00Z",
    "updated_at": "2026-05-28T12:00:00Z"
  },
  "next_ids": {
    "workflow": 1,
    "stage": 1,
    "checklist": 1
  },
  "workflows": [
    {
      "id": 1,
      "title": "Feature Development",
      "description": "Standard flow for adding new features",
      "status": "active",
      "created_at": "2026-05-28T12:00:00Z",
      "updated_at": "2026-05-28T12:00:00Z",
      "archived_at": null,
      "stages": [
        {
          "id": 1,
          "workflow_id": 1,
          "position": 1,
          "title": "Understand",
          "detail": "Clarify scope and inspect relevant files",
          "status": "todo",
          "created_at": "2026-05-28T12:00:00Z",
          "updated_at": "2026-05-28T12:00:00Z",
          "archived_at": null,
          "checklists": [
            {
              "id": 1,
              "stage_id": 1,
              "position": 1,
              "item": "Scope is clarified",
              "required": true,
              "created_at": "2026-05-28T12:00:00Z",
              "updated_at": "2026-05-28T12:00:00Z"
            }
          ]
        }
      ]
    }
  ]
}
```

### `runtime.json`

Local-only state for the active workflow run.

Suggested structure:

```json
{
  "schema_version": 1,
  "next_event_id": 1,
  "runs": {
    "1": {
      "id": 1,
      "workflow_id": 1,
      "current_stage_id": 2,
      "status": "in_progress",
      "started_at": "2026-05-28T12:00:00Z",
      "updated_at": "2026-05-28T12:00:00Z",
      "completed_at": null
    }
  },
  "events": [
    {
      "id": 1,
      "entity_type": "run",
      "entity_id": 1,
      "event_type": "move",
      "payload": {
        "workflow_id": 1,
        "from_stage_id": null,
        "to_stage_id": 1
      },
      "created_at": "2026-05-28T12:00:00Z"
    }
  ]
}
```

## Invariants

- One workflow run has one current stage pointer.
- Stage order is deterministic by `position`.
- Checklist validation reads from the current stage only.
- Advancing to another stage does not require a separate per-stage completion record.
- Runtime changes should not rewrite the tracked definition except when the definition itself changes.

## Default Project Resolution

- Use the current working directory as the default project root.
- Resolve the project root in the command layer so all commands behave consistently.
- Create or update the project root `.gitignore` so `.workflow/runtime.json` remains local.
