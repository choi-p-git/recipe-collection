# Shared Agent Workflow

Use this file with the app-specific context files linked from the root `AGENT.md`.

## Project Posture

This project is a staged MVP for a commercial-kitchen recipe, menu, production, and inventory workflow. Preserve existing lightweight Flask/SQLite patterns unless a feature clearly needs a broader architecture change.

Major route/app boundaries:

- `/recipe-collection`: Recipe Collection, item detail, recipe/base-food authoring, collection APIs.
- `/menus`: Menu Builder, Forecasting, Production Record, service context, production history/reporting.
- `/inventory`: Inventory counts, current on hand, item usage, planning, catalog/match bridge.
- Future `/analytics`: trend, usage, menu, cost, portion-control, and forecast/purchasing analysis.

Shared services may cross app boundaries, but user-facing workflows should keep ownership under their top-level route.

## Agent Behavior

- Read current code before editing; follow local patterns and naming.
- Keep changes scoped to the requested feature/module.
- Do not revert user changes or unrelated dirty files.
- Use service/query layers for business calculations; keep templates simple.
- Add documentation updates when a prompt changes roadmap, constraints, feature status, or deferred direction.
- Prefer durable contracts and explicit semantics over hidden template logic.
- Avoid frontend frameworks unless the project deliberately adopts one.

## Testing Workflow

Start with focused tests for the changed module plus one-level-up route/API coverage when behavior crosses Flask.

Common scoped suites:

- Recipe/detail/scaling: `tests/test_recipe_service.py tests/test_recipe_scaling_service.py tests/test_recipe_flattening_service.py tests/test_recipe_instruction_codec.py`
- Menu/forecast: `tests/test_menu_service.py tests/test_menu_forecast_service.py` plus selected `tests/test_routes.py`
- Production Record: `tests/test_production_record_service.py` plus selected route tests
- Inventory: `tests/test_inventory_service.py tests/test_routes.py --module-scope inventory --relation-scope service,api`
- Database/schema: `tests/test_db_init.py tests/test_db_seed.py`

Use pytest scope options rather than defaulting to the full suite:

```powershell
uv run pytest -q tests --module-scope inventory --relation-scope service,api
```

Reserve full-project pytest for release/regression requests, broad shared-contract edits, dependency/tooling changes, or explicit user request.

## UI Loading Guidance

Keep first screens fast. Heavy calculations should run after explicit navigation or lazy fetch with visible loading state.

`webpage/static/loading_indicator.js` shows the global app loading indicator after 250ms for `window.fetch`, same-window link navigation, and same-window form submits. It starts navigation feedback from the current page before the next document is available, so slow full-page GETs still acknowledge the user's click. Keep this delayed global indicator for user confidence during slower responses, and use feature-local loading/saving states when row- or panel-level context matters.

Reserve blocking overlays/scrims for operations where user interaction must pause to avoid corrupting intent.

## Documentation Workflow

- Root `AGENT.md`: compact entry point and current next steps.
- `docs/agent_context/*.md`: app/service-specific implementation context.
- Dated handoff docs such as `docs/agent_context/handoff_YYYY_MM_DD.md`: temporary resume notes for the next agent/session.
- `README.md`: user-facing current behavior, roadmap, and operating notes.
- Other `docs/*.md`: focused deep dives, refactors, audits, or historical specs.

When changing roadmap or feature status, update the closest relevant app context doc and, if user-facing, `README.md`.

## Handoff Workflow

When the user asks for "handoff", "prepare for handoff", "handoff for next session", "next session handoff", or clearly similar continuity language, create or update a dated handoff doc under `docs/agent_context/` and link the current handoff from `AGENT.md`.

The handoff should be concise but operational:

- Current task state and recent decisions.
- What changed in the working tree.
- Important files touched.
- Last successful verification commands and results.
- Known blockers, caveats, or things not yet done.
- The recommended next slice.
- A commit message candidate when useful.

Handoff docs are not durable architecture docs. Keep durable behavior, roadmap, and constraints in the relevant app context file and `README.md`.
