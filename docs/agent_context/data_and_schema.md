# Data, Schema, And Shared Services Agent Context

## Database

Backend: Python, Flask, SQLite.

Database assets:

- `database/migrations/`: ordered migrations.
- `database/schema.sql`: latest full schema snapshot.
- `src/db.py`: database initialization and migration utilities.

Schema changes must update migrations, schema snapshot, service/query code, route/template surfaces as needed, tests, and docs.

## Shared Services

Shared services include:

- item search
- unit conversion and display
- recipe scaling and flattening
- workflow policy
- user preferences
- inventory bridge contracts
- menu calendar/date helpers

Keep shared services neutral. App-specific routes/templates should stay under their app boundary.

## Controlled Lists

Controlled list modules live in `src/config/`.

Important examples:

- item types
- statuses
- roles
- cooking methods
- item categories
- menu builder configuration
- unit definitions and measurement metadata

Do not scatter controlled-list semantics in templates.

## Dev Automation

`src/dev_automation.py` is back-of-house tooling for creating manual-test operating data after the seed catalog exists.

Current default shape:

- 8 weeks
- Monday-Friday
- breakfast and dinner
- elementary/middle/high concepts

Inventory automation should run after at least one populated menu exists. It parses populated menu cells, expands recipe assignments into flattened base-food ingredients, creates default inventory storage/sub-storage structure, distributes items, and saves randomized case-only count rows through Inventory service paths.

## Validation Checklist

Before considering broad changes complete:

- database initializes from empty DB
- seed/dev automation still creates plausible data when touched
- changed service contracts have focused tests
- changed routes render successfully
- app import smoke test passes:

```powershell
$env:PYTHONPATH='src'; uv run python -c "import app; print('app import ok')"
```
