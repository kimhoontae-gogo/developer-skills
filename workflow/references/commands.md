# Command Surface

## Project Selection

Default project behavior:
- If the user does not specify a project, resolve it from the current directory name.
- If the user specifies a project name or ID, use that value instead.
- `-h` and `--help` are available on the top-level CLI and every subcommand.

## Canonical Commands

- `workflow create-project`
- `workflow list-projects`
- `workflow remove-project`
- `workflow show-project`
- `workflow create-workflow`
- `workflow remove-workflow`
- `workflow list-workflows`
- `workflow show-workflow`
- `workflow list-stages`
- `workflow show-stage`
- `workflow add-stage`
- `workflow update-stage`
- `workflow remove-stage`
- `workflow move-stage`
- `workflow get current`
- `workflow get checklist`
- `workflow get next`
- `workflow move <stage_id>`
- `workflow status`
- `workflow history`

## Read Commands

### `workflow get current`

Return the current stage title, detail, and any stage metadata needed to continue work.

### `workflow get checklist`

Return the checklist for the current stage and enough context to judge whether the stage is truly done.

### `workflow get next`

Return the next stage after the current one, or the best candidate if the user wants to resume from a later point.

### `workflow status`

Return a compact summary of project, workflow, current stage, and overall progress.

### `workflow history`

Return recent state transitions and validation events.

## Mutation Commands

### `workflow move <stage_id>`

Move the runtime pointer to the requested stage.

Use this when:
- The agent is ready to advance after satisfying the current stage checklist.
- The user wants to restart from a later stage.
- Recovery requires jumping back to an earlier stage.
- Moving to a later stage implies the previous current stage is treated as completed in the workflow history.

### `workflow create-*`

Use creation commands to define projects, workflows, and stages before runtime execution begins.

### `workflow remove-project`

Remove a project and recursively remove its workflows, stages, and runtime data.

### `workflow remove-workflow`

Remove a workflow and its stages, checklist entries, and runtime state.

### `workflow add-stage`

Append a new stage to the end of a workflow.

### `workflow update-stage`

Edit a stage title, detail, and optionally replace its checklist.

### `workflow remove-stage`

Remove a stage from the workflow definition and resequence the remaining stages.

### `workflow move-stage`

Reorder a stage within the workflow definition using `--before-stage-id` or `--after-stage-id`.

### `workflow status`

Return a compact progress summary for the current workflow, including the current stage, next stage, and checklist context.

### `workflow history`

Return recent workflow events for debugging or audit trails.

## Validation Rule

- Do not advance from one stage to the next until the checklist for the current stage has been reviewed and satisfied.
