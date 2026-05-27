# Usage

## Entry Point

Use the CLI wrapper as the primary entry point:

```bash
python3 scripts/workflow_cli.py -h
```

## Common Commands

- `python3 scripts/workflow_cli.py create-project --name "hermes-app"`
- `python3 scripts/workflow_cli.py create-workflow --project-name hermes-app --title "Feature Development"`
- `python3 scripts/workflow_cli.py add-stage --workflow-id 1 --title "Understand" --detail "Clarify scope"`
- `python3 scripts/workflow_cli.py update-stage --stage-id 1 --title "Understanding"`
- `python3 scripts/workflow_cli.py move-stage --stage-id 2 --before-stage-id 1`
- `python3 scripts/workflow_cli.py set-stage-order --workflow-id 1 --stage-ids 2 3 1`
- `python3 scripts/workflow_cli.py get-current --project-name hermes-app`
- `python3 scripts/workflow_cli.py get-checklist --project-name hermes-app`
- `python3 scripts/workflow_cli.py get-next --project-name hermes-app`
- `python3 scripts/workflow_cli.py move --project-name hermes-app --stage-id 2`
- `python3 scripts/workflow_cli.py status --project-name hermes-app`
- `python3 scripts/workflow_cli.py history --project-name hermes-app`

## Typical Agent Flow

1. The user asks you to build/fix something.
2. Resolve (or create) the project based on the current directory.
3. Check if a relevant workflow exists for the task type (e.g., "Feature Development", "Bug Fix").
4. If no workflow exists, create one and add stages + checklists.
5. Start execution from the first stage.
6. For each stage:
   a. Read `get-current` to know where you are.
   b. Read `get-checklist` to know what must be done before advancing.
   c. Do the work.
   d. Only after satisfying the checklist, run `move` to the next stage.
7. If the session ends before completion, the next session can resume via `get-current`.

## Notes

- If the user does not specify a project, commands that resolve project context should use the current working directory name.
- The default SQLite database lives at `~/.developer-skills/workflow.sqlite3` unless `WORKFLOW_DB_PATH` or `--db` overrides it.
- `-h` and `--help` are available on the top-level CLI and every subcommand.
