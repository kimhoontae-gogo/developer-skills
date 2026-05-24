# Phase Examples

## Good Example

```md
### Detail
Add structured phase fields so later sessions can resume work from the plan alone.

### Context
This plan is meant to survive session boundaries, so a phase title and one-line note are too thin.

### Approach
Store the handoff brief in separate fields, render them in `show-plan`, and export them in Markdown.

### Files
- `scripts/plan_store.py`
- `references/phase-template.md`
- `references/export-format.md`

### Steps
1. Add schema columns and migration logic.
2. Extend create, add, insert, and update commands.
3. Update human-readable and Markdown output.
4. Verify the new fields survive round-trips.

### Validation
- `python3 -m py_compile scripts/plan_store.py`
- `plan show-plan --plan-id 1`
- `plan export-markdown --plan-id 1`

### Handoff
The next session should confirm that the new fields are visible in both CLI output and Markdown export before moving on.
```

## Weak Example

```md
### Detail
Improve the plan skill.
```

This is too vague because it does not say what to change, where to look, how to validate it, or what the next session should do.

## What Makes the Good Example Better

- It names the implementation surface.
- It gives a concrete sequence of steps.
- It includes validation commands.
- It tells the next session what to verify first.
- It is specific enough to be executed without rereading the full conversation.
