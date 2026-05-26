# Usage

## Entry Point

Use the CLI wrapper as the primary entry point:

```bash
python3 scripts/workflow_cli.py -h
```

## Common Commands

- `python3 scripts/workflow_cli.py create-project --name "developer-skills"`
- `python3 scripts/workflow_cli.py create-workflow --project-name developer-skills --title "Web App" --description "Use this when adding new features to the web application"`
- `python3 scripts/workflow_cli.py update-workflow --project-name developer-skills --title "Web App" --description "Use this when adding new features or enhancing existing UI/UX"`
- `python3 scripts/workflow_cli.py update-project --project-id 1 --description "QueryPie monorepo"`
- `python3 scripts/workflow_cli.py list-workflows --project-name developer-skills`
- `python3 scripts/workflow_cli.py add-stage --workflow-id 1 --title "Plan" --detail "Define scope"`
- `python3 scripts/workflow_cli.py update-stage --stage-id 1 --title "Planning"`
- `python3 scripts/workflow_cli.py move-stage --stage-id 2 --before-stage-id 1`
- `python3 scripts/workflow_cli.py get-current --project-name developer-skills`
- `python3 scripts/workflow_cli.py get-checklist --project-name developer-skills`
- `python3 scripts/workflow_cli.py get-next --project-name developer-skills`
- `python3 scripts/workflow_cli.py move --project-name developer-skills --stage-id 2`
- `python3 scripts/workflow_cli.py status --project-name developer-skills`
- `python3 scripts/workflow_cli.py history --project-name developer-skills`

## Typical Flow

1. Create or resolve the project.
2. List workflows with `list-workflows` and inspect their descriptions.
3. Pick the workflow whose description best matches the user's task. If none match, create one with a clear description.
4. Add stages in execution order.
5. Read `get-current` and `get-checklist` before claiming progress.
6. Use `move` to jump to the stage the user wants to work on.
7. Use `move-stage` only when reordering the workflow definition itself.
8. Use `remove-stage`, `remove-workflow`, and `remove-project` for cleanup.

## Notes

- If the user does not specify a project, commands that resolve project context should use the current working directory name.
- The default SQLite database lives at `~/.developer-skills/workflow.sqlite3` unless `WORKFLOW_DB_PATH` or `--db` overrides it.
- `-h` and `--help` are available on the top-level CLI and every subcommand.
