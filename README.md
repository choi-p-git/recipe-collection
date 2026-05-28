Recipe Collection System
========================

The Recipe Collection System is a modular, database-driven MVP for commercial-kitchen recipe management, menu planning, production forecasting, floor production records, and inventory counts.

The current operating loop is:

Recipe Collection -> Menu Builder -> Forecasting -> Production Record -> Inventory

Future Analytics will consume stable menu, usage, inventory, purchasing, cost, and production-variance contracts after the operational workflows settle.

Project Status
--------------

- Recipe Collection: MVP
- Menu Builder / Forecasting / Production Record: MVP operational vertical
- Inventory: MVP foundation with dedicated planning page
- Analytics: deferred

Architecture
------------

The app is intentionally lightweight:

- Backend: Python, Flask
- Database: SQLite
- UI: server-rendered templates with focused JavaScript
- Schema: forward-only SQL migrations in `database/migrations/`
- Full schema snapshot: `database/schema.sql`

Major route boundaries:

- `/recipe-collection`: recipe/base-food authoring, item detail, collection browsing, recipe APIs
- `/menus`: Menu Builder, Forecasting, Production Record, service context, history/reporting
- `/inventory`: storage locations, current counts, item usage, planning, catalog bridge
- Future `/analytics`: reporting and algorithmic analysis

Current Features
----------------

### Recipe Collection

- Structured recipe records with batch yield, measurement authority, ingredients, methods, instructions, and primary cooking method.
- Lightweight base-food submission flow.
- Shared item detail page for recipes and base foods.
- Live collection browsing and DB-backed item search with exact, prefix, substring, paged, and fuzzy fallback behavior.
- `My Recipes` scoped to the active mock session user.
- Recipe scaling with hierarchical and flattened views, same-family conversion, mass/volume bridge conversion, and display-mode/unit-system toggles.
- Recipe production-sheet print view with active scaling and flattened sub-recipe grouping.
- Advanced hotel-pan units are available for live scaling and Forecasting only, not recipe/base-food authoring.

### Workflow And Auth

- Session-backed mock login for MVP development and role testing.
- Mock account switching and user preferences for display defaults.
- Reviewer, dietitian, and admin workflow portals.
- Workflow history, note threads, returned-to-submitter flow, and notifications.
- Live item detail pages hide advanced workflow details by default, with privileged visibility available.
- Fetch-driven interactions show a delayed loading indicator when requests run longer than 250ms.

### Menu Builder, Forecasting, And Production

- Dated menu cycles with service days, meal periods, concepts, and ordered slot assignments.
- Week/day menu print views.
- Forecasting by yield, desired portions, case mode, advanced hotel-pan units, linked ingredient case packs, and batch splits.
- Production Summary rollups combine assignment forecasts into production-facing totals.
- Production Record snapshots the forecast for a selected service day and supports floor actuals, leftover/shortage, formula-based quantity entry, reason codes, notes, implied demand, forecast accuracy, post/lock, review, CSV export, and print.
- Production Record history/reporting includes filters and summary rollups for accuracy, reason, item, leftover, and shortage.
- Posted Production Records expose `production_record.posted_facts.v1` for future Inventory and Analytics consumers.

### Inventory

- Top-level Inventory app at `/inventory`.
- Main storage locations and sub-storage locations.
- Live base-food count rows with each/case count entry, pack quantity/size/UoM/count-type editing, ordering, break lines, count-sheet printing, transfer scaffolding, and guarded removal.
- Current-on-hand dashboard from active storage-location rows.
- Item detail usage view with count roll-down, upcoming/past menu usage, next need, coverage status, and conversion guard.
- Dedicated `/inventory/planning` page for first-pass reorder/shortage coverage.
- Inventory planning preferences let users define a vendor, check covered item categories, and apply delivery-day-specific cutoff rules plus preferred in-house lead days.
- Inventory catalog and item-match bridge foundation for future invoice/vendor matching.
- `/inventory/catalog/review` review-only page for live base-food catalog matches.

Inventory Notes
---------------

- Inventory counts are operational live counts, not finalized accounting periods.
- Temporary `1 each = quantity/unit` conversions are preview-only operational context and must not be written into Recipe Collection item truth.
- First-pass reorder and shortage planning compares current on hand against next upcoming need, shows `can cover`, `short by`, or review status, and keeps calculated need separate from rounded purchase suggestions.
- Reorder planning uses configured vendor/category ordering preferences to expose vendor, preferred in-house date, planned delivery date, and the cutoff tied to that delivery day. Categories without preferences use a clearly-marked default 7-day planning window.
- Inventory Planning initially shows the next 3 operation days, with the rest of the planning set available behind the page action.
- The base Inventory dashboard links to planning without running the expensive planning calculation during `/inventory` render.
- Catalog review defaults to demand-relevant rows only: current planning-window items, explicit review-needed rows, and auto/vendor-derived matches. `scope=all` is available for admin/audit debugging.
- Future invoice ingest should stage vendor invoice/catalog lines from API, CSV, PDF, or email sources, match by vendor item id/catalog id first, and prompt users to add unmatched items to inventory sub-locations with invoice history attached.
- Future invoice/accounting work should use Inventory purchase UoM and pack setup as the costing bridge, and will need item-level vendor mapping for categories split across multiple vendors.

Development Data
----------------

Empty real databases bootstrap with a reusable seed catalog from `src/seed_catalog.py`:

- 500 commercial-kitchen base foods
- 100 simple recipes
- 100 complex recipes

`src/dev_automation.py` can create randomized menu, forecast, production-record, and inventory operating data for manual workflow testing.

Examples:

```powershell
uv run python src/dev_automation.py --menu-name "Dev Automation Draft Menu" --seed 42
uv run python src/dev_automation.py --inventory --menu-ids 1 --seed 42
```

Validation
----------

Use focused module suites for ordinary development. Full-project pytest is reserved for broad release/regression checks.

Inventory example:

```powershell
uv run pytest -q tests/test_inventory_service.py tests/test_routes.py --module-scope inventory --relation-scope service,api
```

App import smoke test:

```powershell
$env:PYTHONPATH='src'; uv run python -c "import app; print('app import ok')"
```

Database/schema changes should add a numbered migration, update `database/schema.sql`, and run the database/schema tests plus affected module/API tests.

Agent And Architecture Context
------------------------------

Detailed agent-facing implementation guidance has moved out of this README:

- `AGENT.md`: compact context index and current next steps
- `docs/agent_context/shared_agent_workflow.md`: shared agent behavior, testing, loading, docs workflow
- `docs/agent_context/recipe_collection.md`: Recipe Collection rules and roadmap
- `docs/agent_context/menu_builder.md`: Menu Builder, Forecasting, Production Record context
- `docs/agent_context/inventory.md`: Inventory counts, planning, catalog bridge, loading guidance
- `docs/agent_context/data_and_schema.md`: database, shared services, dev automation

Current Roadmap
---------------

1. Scaffold Inventory invoice/catalog staging contracts with a small CSV/manual fixture path.
2. Add invoice line match review and prompt-to-add-to-location workflow for unmatched vendor lines.
3. Add Inventory catalog match editing/confirmation after invoice/catalog review proves the row model.
4. Expand Inventory reorder/shortage planning beyond counted items to include upcoming base-food needs with no current count row.
5. Add item-level vendor/source mapping for invoice/catalog ingestion where category-level vendor rules are not specific enough.
6. Expand Inventory availability from menu item rollups to recipe ingredient demand rollups.
7. Add Forecast/Production forecast-error trend reporting by item over time using posted facts.
8. Refine posted facts only through versioned contract changes.
9. Defer analytics algorithms until usage, menu, inventory, purchasing, and cost record contracts are stable.

Patch Notes
-----------

### v0.0.1

Initial MVP proof-of-concept release:

- Unified item support for recipes and base foods
- Base food submission and duplicate-name handling
- Multi-section recipe editor with validation and ingredient search
- Mock auth shell and user preferences
- Workflow portals, notes, history, returned-to-submitter flow, and notifications
- SQLite migrations and schema snapshot
- Automated validation across schema, services, policies, queries, routes, workflow, notifications, and instruction codec behavior
