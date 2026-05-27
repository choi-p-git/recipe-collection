# Inventory Agent Context

Status: MVP foundation.

Primary route boundary: `/inventory`.

## Current Scope

Inventory is a top-level app for operational counts and early planning:

- Main storage locations and sub-storage locations.
- Live item count rows for live base foods.
- Ordered count rows with visual break lines.
- Each/case count entry, pack quantity/size/UoM/count-type editing.
- Count-sheet print views.
- Transfer scaffolding.
- Price-history placeholders.
- Current-on-hand dashboard rollup from active location item rows.
- Inventory catalog and item-match bridge foundation for future invoice/vendor auto-match.
- Inventory availability service contract consumed by Forecasting Production Summary.
- Item detail usage/coverage view with menu usage, count roll-down, next need, and conversion guard.
- Dedicated `/inventory/planning` page for first-pass reorder/shortage coverage.

## Current On-Hand Semantics

Current on hand sums live item rows across active storage locations by item/unit after normalizing count entry from each/case fields into row quantity.

Inventory counts are live operational counts. There is no independent submit/finalize step in this app. Weekly business finalization belongs to a later finance/accounting layer.

## Identity Boundary

Recipe Collection `item_id` remains culinary ingredient identity.

Inventory owns:

- `inventory_catalog_item`: purchasing/counting/vendor-facing identity.
- `inventory_item_match`: bridge from Recipe Collection item to inventory catalog item.

Current count entry still accepts live base-food `item_id` for MVP continuity. New count rows create a legacy inventory catalog match so future invoice auto-match, vendor catalog import, accounting, and analytics can migrate toward inventory-owned identity.

## Demand And Conversion Governance

Temporary `1 each = quantity/unit` conversions are preview-only operational assumptions. Do not persist them to Recipe Collection item metadata.

Base-food official mass/volume metadata can support each-to-mass/volume conversion when present. Purveyor-, pack-, or operator-specific each assumptions should stay in inventory/vendor/invoice context.

Reorder and shortage planning currently exposes calculated coverage facts only. Future purchase suggestions should use inventory purchase UoM and pack setup while keeping calculated demand separate from rounded order quantities.

## Planning And Loading

`/inventory` must stay fast and render current counts/storage immediately.

Expensive reorder/shortage coverage runs on `/inventory/planning`, not during synchronous `/inventory` dashboard render. If planning later becomes lazy-loaded, it must use visible loading state.

Global fetch loading feedback appears after 250ms through `webpage/static/loading_indicator.js`.

## Agent Implementation Guidance

- Keep Inventory dashboard focused on locations and current on hand.
- Keep planning calculations in service layers, not templates.
- Do not add rounded purchase/order suggestions until calculated need and coverage remain stable.
- Use inventory purchase UoM and pack setup for future ordering suggestions.
- Forecasting and Production Record should consume Inventory through service/API contracts.
- Keep invoice/vendor ingest and accounting logic out of current count services until their contracts exist.

## Testing Guidance

Primary focused suite:

```powershell
uv run pytest -q tests/test_inventory_service.py tests/test_routes.py --module-scope inventory --relation-scope service,api
```

Use route tests when changing:

- `/inventory`
- `/inventory/planning`
- `/inventory/items/<item_id>`
- count APIs
- location/count entry workflows

## Roadmap

1. Add review UI for unmatched, ambiguous, and invoice-auto-matched inventory catalog items.
2. Expand reorder/shortage planning beyond counted items to include upcoming base-food needs with no current count row.
3. Expand inventory availability from menu item rollups to recipe ingredient demand rollups.
4. Add future purchasing suggestions only after calculated need, pack/case setup, and catalog match review are stable.
