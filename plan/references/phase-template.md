# Phase Template

Use this structure for every phase that should survive a handoff between sessions.
The goal is not just to describe what to do, but to give the next session enough context to continue immediately.

## Required Fields

### Detail
One-sentence summary of the outcome.

### Context
Why this phase exists, what came before it, and what later work depends on it.

### Approach
The implementation strategy or execution path.

### Files
The files, modules, scripts, or docs expected to change.

### Steps
The concrete order of work. Use numbered steps when possible.

### Validation
How to confirm the phase is complete.

### Handoff
What the next session should read or verify first if work resumes here.

## Recommended Shape

```md
### Detail
Implement structured phase briefs so another session can continue without extra context.

### Context
The plan is used for session handoff, so a short phase label is not enough to resume safely.

### Approach
Add structured fields to phase storage, render them in human-readable output, and export them in Markdown.

### Files
- `scripts/plan_store.py`
- `references/export-format.md`

### Steps
1. Extend the schema.
2. Update create/update commands.
3. Update show/export output.
4. Add examples and validation commands.

### Validation
- `python3 -m py_compile scripts/plan_store.py`
- `plan show-plan --plan-id 1`
- `plan export-markdown --plan-id 1`

### Handoff
The next session should verify the new fields round-trip through create, update, show, and export.
```

## Writing Rules

- Keep the phase brief specific enough that another session does not need old chat history.
- Mention the implementation surface directly instead of describing work only in abstract terms.
- Include concrete validation commands when the phase touches code or CLI behavior.
- Leave a section empty only if the section truly adds no value for that phase.
