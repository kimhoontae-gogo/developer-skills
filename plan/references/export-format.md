# Markdown Export Format

## Output Order

1. Title
2. Goal
3. Status summary
4. Phase details

## Required Content

- Title must be the plan title.
- Goal must be the plan goal.
- Status must summarize the plan state and all phase states.
- Phase details must appear in execution order.

## Template

```md
# {Plan Title}

## Goal
{Plan Goal}

## Status
- Plan: {Plan Status}
- Current Phase: {Current Phase Title or None}
- Phase 1: {Phase 1 Status}
- Phase 2: {Phase 2 Status}

## Phases
### Phase 1. {Phase 1 Title}
{Phase 1 Detail}

### Phase 2. {Phase 2 Title}
{Phase 2 Detail}
```

## Formatting Rules

- Keep phase order identical to the stored `position`.
- Include every phase, even if it is `done` or `in_progress`.
- Do not attempt reverse parsing from Markdown back into SQLite.
- If the plan is archived, preserve the same structure and show the archived status in the summary.

