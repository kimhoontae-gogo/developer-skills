---
name: plan
description: Manage SQLite-backed project plans with Projects, Plans, and ordered Phases, including status tracking, handoff-ready phase briefs, plan resume support, and Markdown export.
---

# Plan

## Overview

Use this skill to manage SQLite-backed development plans that another session can resume from without extra context.

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
- Use `set-phase-order` to reorder all `todo` phases at once by listing their IDs in the desired order.
- If a section is not applicable, leave it empty only after deciding it is genuinely unnecessary.
- Write phases so another session can continue without external memory or follow-up questions.
- See `references/phase-template.md` for the required phase brief shape.
- See `references/examples.md` for good and weak phase examples.
- See `references/usage.md` for command examples and strict CLI rules.
- See `references/export-format.md` for the Markdown export structure.

## Data Layer

Use the bundled CLI as the primary interface.

- `scripts/plan_cli.py` is the entry point AI should use for plan operations.
- `scripts/plan_store.py` is the internal storage layer used by the CLI and should generally not be called directly.
- The store enforces the phase-order rule at the script level, so invalid moves and starts fail before they can corrupt state.
- The default SQLite database lives at `~/.developer-skills/plan.sqlite3` unless `PLAN_DB_PATH` or `--db` overrides it.
- `-h` / `--help` is available on the CLI and each subcommand via argparse.
