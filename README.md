# developer-skills

AI Agent Skills for planning and workflow management.

This repository contains reusable skill packages that teach an AI agent how to manage structured work with local state instead of ad hoc documents.

## Included Skills

### `plan`

Use when you need a long-lived project plan with ordered phases, status tracking, resume support, and Markdown export.

Typical use cases:
- Break a project into phases
- Insert or reorder todo phases
- Track progress across long-running planning work
- Export a plan as Markdown for sharing

### `workflow`

Use when you need a project-specific execution workflow with ordered stages, checklist validation, runtime stage movement, and cleanup.

Typical use cases:
- Define a workflow under the current project path
- Ask the agent what the current stage is
- Check the checklist before moving forward
- Reorder, update, or remove stages
- Jump back to an earlier stage after review

## Local State

The skills keep their default local state under `~/.developer-skills/` for global planning data:

- `~/.developer-skills/plan.sqlite3`

The `workflow` skill stores project-local definition and runtime files under each repository:

- `[project]/.workflow/definition.json`
- `[project]/.workflow/runtime.json`

The workflow runtime file should stay untracked. The skill updates the project root `.gitignore` to ignore `.workflow/runtime.json` and `.workflow/*.tmp`.

## Quick Start

### Plan

`plan` is for long-lived planning work where you want the agent to keep track of a project goal and a sequence of phases.

1. Create or resolve the project.

```bash
plan create-project --description "Billing work"
```

If you omit `--name`, the current directory name becomes the project name.

2. Create a plan with an explicit goal.

```bash
plan create-plan --project-id 1 --title "Add export" --goal "Export current plans"
```

3. Add phases in the order you expect to execute them.

```bash
plan add-phase --plan-id 1 --title "Design" --detail "Define schema and output"
plan add-phase --plan-id 1 --title "Implement" --detail "Build the feature"
plan add-phase --plan-id 1 --title "Validate" --detail "Check output and edge cases"
```

4. Inspect the plan before moving forward.

```bash
plan show-plan --plan-id 1
plan show-phase --phase-id 2
```

5. Move todo phases when the order changes.

```bash
plan move-phase --phase-id 4 --after-phase-id 3
```

6. Update the plan as the work evolves.

```bash
plan update-plan --plan-id 1 --patch '{"goal":"Export plans to Markdown"}'
plan update-phase --phase-id 2 --patch '{"detail":"Implement export and formatting"}'
```

7. Export once the plan is ready to share.

```bash
plan export-markdown --plan-id 1
```

### Workflow

`workflow` is for execution flow. It is meant to answer questions like:
- What is the current stage?
- What should I check before moving on?
- What is the next stage?
- Which stage should I jump back to after a review?

1. Initialize the current project directory.

```bash
python3 scripts/workflow_cli.py create-project --name "hermes-app"
```

If you do not pass `--name`, the current directory name is used.

2. Create a workflow under the current project path.

```bash
python3 scripts/workflow_cli.py create-workflow --title "Web App" --description "Standard feature flow"
```

3. Add stages to the workflow.

```bash
python3 scripts/workflow_cli.py add-stage --workflow-id 1 --title "Plan" --detail "Define scope"
python3 scripts/workflow_cli.py add-stage --workflow-id 1 --title "Implement" --detail "Build the feature"
python3 scripts/workflow_cli.py add-stage --workflow-id 1 --title "Review" --detail "Check the result with the user"
```

4. Attach checklists when a stage needs a clear definition of done.

```bash
python3 scripts/workflow_cli.py add-stage \
  --workflow-id 1 \
  --title "Validate" \
  --detail "Confirm the output" \
  --checklist '{"item":"Expected result is visible","required":true}' \
  --checklist '{"item":"No regressions in the changed area","required":true}'
```

5. Ask the agent where it is and what to do next.

```bash
python3 scripts/workflow_cli.py get-current
python3 scripts/workflow_cli.py get-checklist
python3 scripts/workflow_cli.py get-next
python3 scripts/workflow_cli.py status --json
```

6. Move the runtime pointer to the stage you want to work on.

```bash
python3 scripts/workflow_cli.py move --stage-id 2
```

This is the command you use when:
- You want to resume from the next stage
- A user wants to jump back to an earlier stage
- A review changes the plan and you need to restart from a specific point

7. Reorder, update, or remove stage definitions when the workflow itself changes.

```bash
python3 scripts/workflow_cli.py move-stage --stage-id 3 --before-stage-id 2
python3 scripts/workflow_cli.py update-stage --stage-id 2 --title "Implementation"
python3 scripts/workflow_cli.py remove-stage --stage-id 4
```

8. Clean up the workflow or project when the work is finished.

```bash
python3 scripts/workflow_cli.py remove-workflow --workflow-id 1
python3 scripts/workflow_cli.py remove-project
```

## How To Choose

- Use `plan` when you want a long-lived plan with phases that support planning and export.
- Use `workflow` when you want the agent to operate like a stage-driven executor that can inspect, move, and resume work.

## Conventions

- Keep skill-specific instructions inside each skill directory.
- Keep low-level command details in `references/` instead of the root README.
- Store `plan` state globally under `~/.developer-skills/`.
- Store `workflow` definition and runtime state inside each project under `.workflow/`.
- Do not commit local runtime files or virtual environments.

## Repository Layout

```text
plan/
  SKILL.md
  references/
  scripts/
workflow/
  SKILL.md
  references/
  scripts/
```
