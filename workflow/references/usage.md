# Usage

## Entry Point

Use the CLI wrapper as the primary entry point:

```bash
python3 scripts/workflow_cli.py -h
```

## Common Commands

- Override the project root when you are not running from the repo root:

```bash
python3 scripts/workflow_cli.py --project-path /path/to/repo create-project --name "hermes-app"
```

- `python3 scripts/workflow_cli.py create-project --name "hermes-app"`
- `python3 scripts/workflow_cli.py update-project --description "Hermes Agent console workspace"`
- `python3 scripts/workflow_cli.py create-workflow --title "Feature Development" --description "Standard flow for adding new features"`
- `python3 scripts/workflow_cli.py update-workflow --workflow-id 1 --description "Use this when adding or extending web app features"`
- `python3 scripts/workflow_cli.py add-stage --workflow-id 1 --title "Understand" --detail "Clarify scope" --checklist '{"item":"Scope is clarified with the user","required":true}'`
- `python3 scripts/workflow_cli.py update-stage --stage-id 1 --title "Understand the request"`
- `python3 scripts/workflow_cli.py move-stage --stage-id 2 --before-stage-id 1`
- `python3 scripts/workflow_cli.py set-stage-order --workflow-id 1 --stage-ids 2 3 1`
- `python3 scripts/workflow_cli.py get-current`
- `python3 scripts/workflow_cli.py get-checklist`
- `python3 scripts/workflow_cli.py get-next`
- `python3 scripts/workflow_cli.py move --stage-id 2`
- `python3 scripts/workflow_cli.py status`
- `python3 scripts/workflow_cli.py history`

## Typical Agent Flow

1. Start from the current working directory unless the user specifies a different project path.
2. Run `create-project` once for the project root.
3. Create a workflow for the task type the user requested.
4. Add stages and checklists that describe the implementation path.
5. Use `get-current` and `get-checklist` before claiming a stage is done.
6. Use `move` to advance the runtime pointer after validation passes.
7. Use `move-stage` or `set-stage-order` only when the definition order changes.
8. If the session ends, the next session can resume from `runtime.json`.
9. If `workflow-id` is omitted, the command layer uses the latest active workflow in the project.

## File Layout

- `[project]/.workflow/definition.json` stores the tracked workflow definition.
- `[project]/.workflow/runtime.json` stores local runtime state and is ignored.
- `[project]/.gitignore` should keep `.workflow/runtime.json` untracked.
