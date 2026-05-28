# Agent Context Index

This file is the compact entry point for Codex/agent work in this repo. Load the app-specific context file for the module you are changing.

## Project Purpose

Recipe Collection is a staged MVP for a commercial-kitchen operating loop:

Recipe Collection -> Menu Builder -> Forecasting -> Production Record -> Inventory -> future Analytics.

The app is intentionally lightweight: Python, Flask, SQLite, server-rendered templates, focused JavaScript, and service/query-layer business logic.

## Context Files

- Shared agent workflow, testing, loading, and documentation rules: `docs/agent_context/shared_agent_workflow.md`
- Recipe Collection, item identity, recipe/base-food authoring, search, scaling: `docs/agent_context/recipe_collection.md`
- Menu Builder, Forecasting, Production Record, posted facts, reporting: `docs/agent_context/menu_builder.md`
- Inventory counts, catalog bridge, item usage, planning, loading guidance: `docs/agent_context/inventory.md`
- Database, schema, shared services, dev automation: `docs/agent_context/data_and_schema.md`
- Current task handoff/resume note: `docs/agent_context/handoff_2026_05_28.md`
- Popover governance refactor history: `docs/popover_governance_refactor.md`

## Current Architecture

Primary route/app boundaries:

- `/recipe-collection`: Recipe Collection, recipe/base-food authoring, item detail, collection APIs.
- `/menus`: Menu Builder, Forecasting, Production Record, service context, production history/reporting.
- `/inventory`: Inventory counts, current on hand, item usage, planning, catalog/match bridge.
- Future `/analytics`: trend, usage, menu, cost, portion-control, and forecast/purchasing analysis.

Shared services may be reused across apps, but user-facing screens and workflows should preserve clear route ownership.

## Current App Status

- Recipe Collection: MVP.
- Menu Builder / Forecasting / Production Record: MVP operational vertical.
- Inventory: MVP foundation with dedicated planning and catalog review pages.
- Analytics: deferred.

## Current Next Logical Development Steps

1. Scaffold Inventory invoice/catalog staging contracts with a small CSV/manual fixture path.
2. Add invoice line match review and prompt-to-add-to-location workflow for unmatched vendor lines.
3. Add Inventory catalog match editing/confirmation after invoice/catalog review proves the row model.
4. Expand Inventory reorder/shortage planning beyond counted items to include upcoming base-food needs with no current count row.
5. Expand Inventory availability from menu item rollups to recipe ingredient demand rollups.
6. Add Forecast/Production forecast-error trend reporting by item over time using posted facts.
7. Refine posted facts only through versioned contract changes.
8. Defer analytics algorithms until usage, menu, inventory, purchasing, and cost record contracts are stable.

## Agent Workflow

- Read the relevant context file before changing a module.
- Keep changes scoped and follow existing service/query/template patterns.
- Do not revert user changes or unrelated dirty files.
- Put business calculations in service/query layers, not templates.
- Update `README.md` for user-facing current behavior/roadmap changes.
- Update the relevant `docs/agent_context/*.md` file for agent-facing constraints, semantics, and next steps.
- When asked for handoff/next-session continuity, create or update a dated `docs/agent_context/handoff_YYYY_MM_DD.md` and link it above.
- Use focused pytest scopes for the changed module; reserve full-project pytest for broad regression/release work.

## Common Verification

Inventory:

```powershell
uv run pytest -q tests/test_inventory_service.py tests/test_routes.py --module-scope inventory --relation-scope service,api
```

App import:

```powershell
$env:PYTHONPATH='src'; uv run python -c "import app; print('app import ok')"
```
