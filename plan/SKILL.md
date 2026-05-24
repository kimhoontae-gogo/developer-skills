---
name: plan
description: Manage SQLite-backed project plans with Projects, Plans, and ordered Phases, including status tracking, plan resume support, and Markdown export.
---

# Plan

## Overview

Use this skill to create, inspect, update, and export structured development plans stored in SQLite.
It is designed for long-lived planning work where another session must be able to resume from the current state.

## Operating Rules

- A `Project` is the top-level container and has many `Plan` records.
- A `Plan` belongs to exactly one `Project`.
- A `Plan` has a title, goal, status, and ordered phases.
- A `Phase` has a title, detail, status, and position.
- Phase execution is always sequential.
- Only `todo` phases may be inserted or moved.
- `in_progress` and `done` phases are fixed in place.
- `todo` phases may only move within the `todo` section.
- `todo` phases may not move ahead of `in_progress` or `done` phases.
- After any status change, recompute the plan summary state.

## Data Layer

Use the bundled CLI as the primary interface.

- `scripts/plan_cli.py` is the entry point AI should use for plan operations.
- `scripts/plan_store.py` is the internal storage layer used by the CLI and should generally not be called directly.
- The store enforces the phase-order rule at the script level, so invalid moves and starts fail before they can corrupt state.

## Common Examples

- `plan create-project --name "Payments" --description "Billing work"`
- `plan create-plan --project-id 1 --title "Add export" --goal "Export current plans"`
- `plan show-plan --plan-id 1`
- `plan show-phase --phase-id 2`
- `plan update-plan --plan-id 1 --patch '{"goal":"Export plans to Markdown"}'`
- `plan start-phase --phase-id 2`
- `plan complete-phase --phase-id 2`

## References

- See [usage.md](references/usage.md) for concrete commands and examples.
- See [export-format.md](references/export-format.md) for the Markdown export structure.
- `-h` / `--help` is available on the CLI and each subcommand via argparse.
