# Command Surface

## Project Selection

- The default project is the current working directory.
- Override the project root with `--project-path <path>` when needed.
- If `--workflow-id` is omitted, select the latest active workflow in the current project.
- The CLI exposes `-h` / `--help` on the top level and every subcommand.

## Canonical Commands

- `workflow create-project`
- `workflow update-project`
- `workflow list-projects`
- `workflow show-project`
- `workflow remove-project`
- `workflow create-workflow`
- `workflow update-workflow`
- `workflow remove-workflow`
- `workflow list-workflows`
- `workflow show-workflow`
- `workflow list-stages`
- `workflow show-stage`
- `workflow add-stage`
- `workflow update-stage`
- `workflow remove-stage`
- `workflow move-stage`
- `workflow set-stage-order`
- `workflow get-current`
- `workflow get-checklist`
- `workflow get-next`
- `workflow move <stage_id>`
- `workflow status`
- `workflow history`

## Project Commands

### `workflow create-project`

Initialize `[project]/.workflow/`, create `definition.json` and `runtime.json`, and update the project root `.gitignore` to exclude `.workflow/runtime.json`.

### `workflow update-project`

Update project metadata stored in `definition.json`.

### `workflow list-projects`

Return the current project record if it is initialized.

### `workflow show-project`

Return the project metadata plus workflow summaries.

### `workflow remove-project`

Delete the local workflow files under `[project]/.workflow/`.

## Workflow Commands

### `workflow create-workflow`

Create a workflow definition inside the current project.

### `workflow update-workflow`

Update a workflow title or description.

### `workflow remove-workflow`

Remove a workflow and its stages from the project definition and runtime state.

### `workflow list-workflows`

List all workflows for the current project.

### `workflow show-workflow`

Return the selected workflow, its stages, and current runtime state.

## Stage Commands

### `workflow add-stage`

Append a stage to a workflow.

### `workflow update-stage`

Update a stage title, detail, and optionally replace the checklist.

### `workflow remove-stage`

Remove a stage and resequence the remaining stages.

### `workflow move-stage`

Move one stage before or after another stage inside the same workflow.

### `workflow set-stage-order`

Replace the active stage order by listing the stage IDs in the desired order.

### `workflow list-stages`

List stages for the selected workflow in order.

### `workflow show-stage`

Return one stage plus its checklist items.

## Runtime Commands

### `workflow get-current`

Return the current runtime pointer and the current stage, if any.

### `workflow get-checklist`

Return the current stage checklist.

### `workflow get-next`

Return the next stage after the current one, or the first stage when the run has not started.

### `workflow move <stage_id>`

Move the runtime pointer to a specific stage.

### `workflow status`

Return a compact progress summary for the selected workflow.

### `workflow history`

Return recent runtime events for the selected workflow.

## Validation Rule

- Do not move forward until the current stage checklist has been reviewed and satisfied.
