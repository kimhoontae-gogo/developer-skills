# Plan Skill Usage

## Common Commands

- Create a project: `plan create-project --name "Payments" --description "Billing work"`
- Update a project: `plan update-project --project-id 1 --description "Updated description"`
- List projects: `plan list-projects`
- Show one project: `plan show-project --project-id 1`
- Create a plan: `plan create-plan --project-id 1 --title "Add export" --goal "Export current plans"`
- Add phases: `plan add-phase --plan-id 1 --title "Design" --detail "Define schema and output"`
- Insert a phase: `plan insert-phase --plan-id 1 --before-phase-id 2 --title "Review" --detail "Check API shape"`
- Move a todo phase: `plan move-phase --phase-id 4 --after-phase-id 3`
- Show a plan: `plan show-plan --plan-id 1`
- Show a phase: `plan show-phase --phase-id 2`
- Start a phase: `plan start-phase --phase-id 2`
- Complete a phase: `plan complete-phase --phase-id 2`
- Export Markdown: `plan export-markdown --plan-id 1`

## Notes

- `update-plan` and `update-phase` accept `--patch` JSON for multi-field updates.
- `insert-phase` and `move-phase` only allow `todo` phases and only within the `todo` section.
- `show-plan` and `show-phase` default to human-readable output; add `--json` for structured output.
- `-h` / `--help` is available on `plan_cli.py` and every subcommand via argparse.
