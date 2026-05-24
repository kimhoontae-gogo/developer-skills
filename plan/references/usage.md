# Plan Skill Usage

## Common Commands

- Create a project: `plan create-project --name "Payments" --description "Billing work"`
- Create a project from the current directory: `plan create-project --description "Billing work"`
- Update a project: `plan update-project --project-id 1 --description "Updated description"`
- List projects: `plan list-projects`
- Show one project: `plan show-project --project-id 1`
- Create a plan: `plan create-plan --project-id 1 --title "Add export" --goal "Export current plans"`
- Add a detailed phase: `plan add-phase --plan-id 1 --title "Design" --detail "Define schema and output" --context "This is the first implementation pass and will be resumed by another session if interrupted." --approach "Begin with the schema and then update the CLI and export path." --files "scripts/plan_store.py,references/export-format.md" --steps "1. Add columns. 2. Add CLI flags. 3. Update display and export output." --validation "show-plan and export-markdown both render the new fields." --handoff "The next session should check that create/update/export round-trip all brief fields."`
- Insert a detailed phase: `plan insert-phase --plan-id 1 --before-phase-id 2 --title "Review" --detail "Check API shape" --context "The previous implementation phase should be reviewed before it starts." --approach "Validate the data model and keep the workflow narrow." --files "scripts/plan_store.py" --steps "1. Review the schema. 2. Adjust the CLI if needed. 3. Re-run validation." --validation "The phase can be resumed directly from show-phase output." --handoff "Start by confirming the schema change is present in the current DB."`
- Move a todo phase: `plan move-phase --phase-id 4 --after-phase-id 3`
- Show a plan: `plan show-plan --plan-id 1`
- Show a phase: `plan show-phase --phase-id 2`
- Start a phase: `plan start-phase --phase-id 2`
- Complete a phase: `plan complete-phase --phase-id 2`
- Export Markdown: `plan export-markdown --plan-id 1`

## Notes

- `update-plan` and `update-phase` accept `--patch` JSON for multi-field updates.
- `update-phase` still requires a complete brief: `title`, `detail`, `context`, `approach`, `files`, `steps`, `validation`, and `handoff` must all be present either directly or inside `--patch`.
- `create-plan --phase` can pre-seed a phase, but each phase JSON object must include `title`, `detail`, `context`, `approach`, `files`, `steps`, `validation`, and `handoff`.
- `add-phase` and `insert-phase` require all brief fields on the command line, even if some values are empty strings.
- `insert-phase` and `move-phase` only allow `todo` phases and only within the `todo` section.
- `show-plan` and `show-phase` default to human-readable output; add `--json` for structured output.
- The default SQLite database lives at `~/.developer-skills/plan.sqlite3` unless `PLAN_DB_PATH` or `--db` overrides it.
- `-h` / `--help` is available on `plan_cli.py` and every subcommand via argparse.
- `detail`, `context`, `approach`, `files`, `steps`, `validation`, and `handoff` are the intended phase-brief fields; leave a field empty only when it is genuinely unnecessary.
