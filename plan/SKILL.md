---
name: plan
description: Manage SQLite-backed project plans with Projects, Plans, and ordered Phases, including status tracking, handoff-ready phase briefs, plan resume support, and Markdown export.
---

# Plan

## Overview

Use this skill to create, inspect, update, and export structured development plans stored in SQLite.
It is designed for long-lived planning work where another session must be able to resume from the current state.

## Operating Rules

- A `Project` is the top-level container and has many `Plan` records.
- A `Plan` belongs to exactly one `Project`.
- A `Plan` has a title, goal, status, and ordered phases.
- A `Phase` has a title, detail, status, position, and a structured execution brief.
- Phase execution is always sequential.
- Only `todo` phases may be inserted or moved.
- `in_progress` and `done` phases are fixed in place.
- `todo` phases may only move within the `todo` section.
- `todo` phases may not move ahead of `in_progress` or `done` phases.
- After any status change, recompute the plan summary state.
- If `create-project` is called without `--name`, use the current working directory name.
- Every phase must be written as a reusable execution brief, not just a one-line task label.
- Every phase should include `detail`, `context`, `approach`, `files`, `steps`, `validation`, and `handoff`.
- If a section is not applicable, leave it empty only after deciding it is genuinely unnecessary.
- Write phases so another session can continue without external memory or follow-up questions.
- `add-phase` and `insert-phase` require every brief field at the CLI level.
- `create-plan --phase` requires every brief field in each JSON object.
- `update-phase` requires every brief field either as direct CLI values or inside `--patch`.
- Prefer the phase template in `references/phase-template.md` when creating or updating phases.
- Keep examples in `references/examples.md` aligned with the current schema and CLI.

## Data Layer

Use the bundled CLI as the primary interface.

- `scripts/plan_cli.py` is the entry point AI should use for plan operations.
- `scripts/plan_store.py` is the internal storage layer used by the CLI and should generally not be called directly.
- The store enforces the phase-order rule at the script level, so invalid moves and starts fail before they can corrupt state.
- The default SQLite database lives at `~/.developer-skills/plan.sqlite3` unless `PLAN_DB_PATH` or `--db` overrides it.

## Common Examples

- `plan create-project --name "Payments" --description "Billing work"`
- `plan create-project --description "Billing work"`
- `plan create-plan --project-id 1 --title "Add export" --goal "Export current plans"`
- `plan add-phase --plan-id 1 --title "Design" --detail "Design the export flow" --context "This plan is resumed across sessions, so the next agent needs implementation context." --approach "Start with the data model, then update export formatting and CLI output." --files "scripts/plan_store.py,references/export-format.md" --steps "1. Add schema support. 2. Render the new fields. 3. Update examples." --validation "show-plan and export-markdown both include the structured brief." --handoff "Next session should verify that create/update/export all preserve the phase brief."`
- `plan show-plan --plan-id 1`
- `plan show-phase --phase-id 2`
- `plan update-plan --plan-id 1 --patch '{"goal":"Export plans to Markdown"}'`
- `plan update-phase --phase-id 2 --patch '{"title":"Design","detail":"Design the export flow","context":"The plan needs a resumed handoff.","approach":"Start from the schema.","files":"scripts/plan_store.py,references/export-format.md","steps":"1. Extend schema. 2. Update CLI. 3. Render the new fields.","validation":"show-plan and export-markdown both include the brief.","handoff":"Next session should verify round-tripping before implementation continues."}'`
- `plan start-phase --phase-id 2`
- `plan complete-phase --phase-id 2`

## References

- See [phase-template.md](references/phase-template.md) for the required phase brief structure.
- See [examples.md](references/examples.md) for good and weak phase examples.
- See [usage.md](references/usage.md) for concrete commands and examples.
- See [export-format.md](references/export-format.md) for the Markdown export structure.
- `-h` / `--help` is available on the CLI and each subcommand via argparse.
