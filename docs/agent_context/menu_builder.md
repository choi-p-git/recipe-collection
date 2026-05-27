# Menu Builder, Forecasting, And Production Agent Context

Status: MVP.

Primary route boundary: `/menus`.

## Current Scope

Menu Builder is a separate planning shell over Recipe Collection items:

- Dated menu cycles with weeks, service days, meal periods, concepts, and ordered slots.
- Slot assignment for live recipes and base foods.
- Bulk planning actions and week/day print views.
- Forecasting with yield scaling, user-serving targets, case mode, advanced hotel-pan display, saved item case packs, batch splits, and production summary rollups.
- Production Record as the floor workflow after Forecasting, including actual production, leftover/shortage, reason/notes, implied demand, accuracy, post/lock, review, CSV export, print, history, and reporting.
- Service context page combining forecast and production-record context for a selected service date.

## Menu Data Model

Core tables:

- `menu`: planning cycle, date range, service days, meal periods, concepts, status, author.
- `menu_slot`: schedulable grid cell by week/day/meal/concept.
- `menu_slot_item`: ordered live item assignments inside a slot.

Concept order is a menu-level layout contract. Reordering concepts changes display order only and must not change slot identity or assigned items.

## Forecasting Semantics

- Forecast grid is assignment-oriented; production summary is item-oriented rollup.
- Forecasting supports display quantity/unit and effective calculated quantity/unit, especially for case mode.
- Case mode stores visible `case` forecast while calculated production yield is stored separately.
- Advanced case mode may link to one recipe ingredient so recipe-yield and user-serving calculations can remain available.
- Batch split rows include optional planned time.
- Forecasting occurrence history may include posted and draft/current filled production records because managers need operational memory while forecasting.

## Production Record Semantics

Current data flow:

Menu Builder assignment -> Forecasting -> Production Summary -> Production Record snapshot -> line actuals and end-service variance -> implied demand and forecast accuracy -> posted review/print/export/reporting.

Important fields:

- `actual_production_quantity`: floor-entered produced amount.
- signed `end_service_variance_quantity`: positive leftover, negative shortage.
- `leftover_quantity` / `shortage_quantity`: non-negative downstream split.
- `implied_demand_quantity`: actual production minus signed variance.
- Forecast accuracy is calculated against implied demand, not raw actual production.
- Posted facts at `production_record.posted_facts.v1` are the current downstream source-of-truth contract for Inventory and Analytics. Drafts remain operational memory and are excluded from posted facts.

## Reporting

Implemented reporting includes filters for date range, week/day, status, accuracy, reason, and item, with summary rollups for accurate/review/miss counts, top reason codes, and leftover/shortage totals by item.

Future reporting:

- Forecast error trend by item over time.
- Posted-only analytics defaults while keeping draft inclusion explicit.

## Agent Implementation Guidance

- Keep report calculations in service/query layers, not templates.
- Preserve formula text separately from calculated numeric values.
- Forecasting and Production Record should consume Inventory through services/API contracts, not direct inventory table reads.
- Do not add algorithmic suggested forecasts until occurrence/history/reporting UI is stable.
- Keep drag-and-drop, rules engine, richer batch timing, and analytics deferred unless explicitly pulled in.

## Testing Guidance

Menu Builder service:

```powershell
uv run pytest -q tests/test_menu_service.py --module-scope menu --relation-scope service
```

Forecasting and production summary:

```powershell
uv run pytest -q tests/test_menu_forecast_service.py --module-scope forecast --relation-scope service
```

Production Record:

```powershell
uv run pytest -q tests/test_production_record_service.py --module-scope production --relation-scope service
```

Route/API changes should include selected `tests/test_routes.py` nodes or scoped route tests.

## Roadmap

- Add forecast error trend reporting by item using posted facts.
- Refine posted facts only through versioned contract changes.
- Keep future Analytics consumption focused on posted facts, menu/usage/inventory/purchasing/cost contracts, and stable variance semantics.
