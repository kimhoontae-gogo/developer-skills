# Markdown Export Format

## Output Order

1. Title
2. Goal
3. Status summary
4. Phase details with brief subsections

## Required Content

- Title must be the plan title.
- Goal must be the plan goal.
- Status must summarize the plan state and all phase states.
- Phase details must appear in execution order.
- Each phase should export its `detail` plus any non-empty brief sections.

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

#### Context
{Phase 1 Context}

#### Approach
{Phase 1 Approach}

#### Files
{Phase 1 Files}

#### Steps
{Phase 1 Steps}

#### Validation
{Phase 1 Validation}

#### Handoff
{Phase 1 Handoff}

### Phase 2. {Phase 2 Title}
{Phase 2 Detail}
```

## Formatting Rules

- Keep phase order identical to the stored `position`.
- Include every phase, even if it is `done` or `in_progress`.
- Omit brief subsections when the stored value is empty.
- Do not attempt reverse parsing from Markdown back into SQLite.
- If the plan is archived, preserve the same structure and show the archived status in the summary.
- Keep the brief subsections directly under each phase so a later session can recover the implementation context from the export alone.
