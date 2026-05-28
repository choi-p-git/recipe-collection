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
- `/inventory/catalog/review` page for reviewing live base-food inventory catalog matches.
- Inventory availability service contract consumed by Forecasting Production Summary.
- Item detail usage/coverage view with menu usage, count roll-down, next need, and conversion guard.
- Dedicated `/inventory/planning` page for first-pass reorder/shortage coverage.
- `/inventory/planning/preferences` page for user-specific vendor/category ordering preferences.

## Current On-Hand Semantics

Current on hand sums live item rows across active storage locations by item/unit after normalizing count entry from each/case fields into row quantity.

Inventory counts are live operational counts. There is no independent submit/finalize step in this app. Weekly business finalization belongs to a later finance/accounting layer.

## Identity Boundary

Recipe Collection `item_id` remains culinary ingredient identity.

Inventory owns:

- `inventory_catalog_item`: purchasing/counting/vendor-facing identity.
- `inventory_item_match`: bridge from Recipe Collection item to inventory catalog item.

Current count entry still accepts live base-food `item_id` for MVP continuity. New count rows create a legacy inventory catalog match so future invoice auto-match, vendor catalog import, accounting, and analytics can migrate toward inventory-owned identity.

Catalog review is review-only in the current slice. Default `/inventory/catalog/review` scope is intentionally narrow: current planning-window items, explicit review-needed rows, and auto/vendor-derived matches. Use `?scope=all` only for admin/audit/debug review of all live base foods. The page surfaces unmatched, legacy, auto/vendor-derived, review-needed, and manual matches, but does not yet edit matches or ingest invoices.

## Demand And Conversion Governance

Temporary `1 each = quantity/unit` conversions are preview-only operational assumptions. Do not persist them to Recipe Collection item metadata.

Base-food official mass/volume metadata can support each-to-mass/volume conversion when present. Purveyor-, pack-, or operator-specific each assumptions should stay in inventory/vendor/invoice context.

Reorder and shortage planning currently exposes calculated coverage facts only. Future purchase suggestions should use inventory purchase UoM and pack setup while keeping calculated demand separate from rounded order quantities.

Vendor/category ordering preferences are user-specific. The UX is vendor-first: users enter a vendor, check covered item categories, select `daily`, `as_needed`, or `custom` ordering frequency, configure delivery-day-specific cutoff rules, and set preferred in-house lead days. The storage remains one active row per user/category for fast planning lookup. Planning rows should expose menu usage date, preferred in-house date, planned delivery date, the cutoff deadline tied to that delivery day, vendor, and coverage status so users can understand why an item appears.

Current preference deletion is soft deletion of the active category rule. Future vendor/invoice work must support item-specific vendor resolution below category level, because one category can split across vendors by item or vendor catalog line, such as frozen bread from a broadliner and frozen desserts from a dairy/ice-cream vendor.

## Planning And Loading

`/inventory` must stay fast and render current counts/storage immediately.

Expensive reorder/shortage coverage runs on `/inventory/planning`, not during synchronous `/inventory` dashboard render. Planning uses vendor/category preferences when configured and otherwise falls back to a clearly-marked 7-day default window. The default planning view shows the next 3 operation days first and lets users load the full planning set from the page action. Slow planning navigation should rely on the global delayed loading indicator; if planning later becomes lazy-loaded, it must also use visible loading state.

Global loading feedback appears after 250ms through `webpage/static/loading_indicator.js` for fetch requests, same-window links, and same-window form submits.

## Agent Implementation Guidance

- Keep Inventory dashboard focused on locations and current on hand.
- Keep planning calculations in service layers, not templates.
- Do not add rounded purchase/order suggestions until calculated need and coverage remain stable.
- Use inventory purchase UoM and pack setup for future ordering suggestions.
- Keep vendor preference date/window calculations in `services.inventory_ordering_service`; planning rollups should consume those service outputs.
- Keep catalog review demand-driven. Do not default users into reviewing every live Recipe Collection base food; only surface rows relevant to current planning, invoice/catalog ingest, or explicit review flags.
- Forecasting and Production Record should consume Inventory through service/API contracts.
- Keep invoice/vendor ingest and accounting logic out of current count services until their contracts exist.

## Invoice And Vendor Pipeline Direction

Future invoice/vendor ingest should be a staged pipeline, not a full accounting module at first:

- Vendors may provide API invoices, CSV invoices/catalog exports, PDF invoices, or emailed invoice attachments.
- Ingest should parse invoice lines into staging rows with vendor, invoice identity, SKU/item/catalog id, vendor product category code, item name, pack-size description, quantity, unit, and unit price.
- Vendor product category codes should map through admin-maintained vendor category flags/rules before they influence inventory category or location behavior.
- Matching should first use vendor item id/catalog id and existing inventory catalog vendor-code links, then fall back to reviewable name/category matching.
- If a parsed invoice line is not already matched to current inventory, prompt the user to add or link the item to the correct inventory sub-location.
- Once linked, invoice history should be tagged to the inventory/catalog item so purchasing cost, pack setup, vendor source, and future reorder planning can use actual vendor data.
- Automatic invoice generation for menu-needed items should come later, after invoice line staging, matching, location-link prompts, and reorder planning contracts are stable.
- Current seed/live Recipe Collection items are not the long-term source of inventory catalog truth; inventory automation scripts should migrate toward invoice/catalog-driven item establishment.

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

1. Scaffold invoice/catalog staging tables and import/service contracts with a small CSV/manual fixture path.
2. Add invoice line match review for unmatched or ambiguous vendor lines and prompt-to-add-to-location workflow.
3. Add catalog match editing/confirmation actions after invoice/catalog review proves the row model.
4. Expand reorder/shortage planning beyond counted items to include upcoming base-food needs with no current count row.
5. Expand inventory availability from menu item rollups to recipe ingredient demand rollups.
6. Add vendor item/source mapping for invoice and catalog ingestion so planning can resolve vendor by item, not only by category.
7. Add future purchasing suggestions only after calculated need, pack/case setup, and catalog match review are stable.
