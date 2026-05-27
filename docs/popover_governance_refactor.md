# Shared Popover Governance Refactor

## Goal

Move repeated hover/click/pin popover behavior into one reusable frontend controller while keeping feature-specific markup and rendering independent.

The first pass preserved page behavior while moving the shared surfaces to neutral `app-popover*` classes. Legacy `menu-forecast-history*` selectors remain as CSS compatibility aliases.

## Shared Governance Contract

- Hover open is delayed by a controller-owned timer.
- Pointer leave cancels pending hover-open and pending fetch timers.
- Click toggles/pins immediately for explicit user intent.
- Opening one popover closes other open popovers in the same controller group.
- Outside click closes open popovers.
- `Escape` closes open popovers.
- Loaded lazy panels are cached in the DOM for the current page session.
- CSS must not expose hover popovers via `:hover`; mouse hover visibility must be controlled by JS.
- CSS may preserve `:focus-within` visibility for keyboard accessibility unless the controller introduces an equivalent focus governance path.

## Existing Popover And Overlay Inventory

### Inventory Dashboard

- Template: `webpage/templates/inventory.html`
- Controller today: `webpage/static/inventory.js`
- CSS: `webpage/static/styles.css`
- Markup:
  - `data-popover`
  - `data-popover-trigger`
  - `data-popover-panel`
  - `data-inventory-usage-panel`
  - `data-inventory-count-panel`
- Content mode: lazy JSON fetch.
- Endpoints:
  - `/api/inventory/items/<item_id>/usage-summary`
  - `/api/inventory/items/<item_id>/count-rolldown`
- Current timing:
  - hover visual open: 500ms
  - hover fetch intent: 650ms
  - click: immediate open and fetch
- Independent behavior:
  - item name trigger is an anchor; click navigates.
  - quantity/location triggers are buttons; click pins/toggles.
  - fetched content is rendered by inventory-specific JS renderers.

### Menu Forecast History

- Template: `webpage/templates/menu_forecast.html`
- Controller today: `webpage/static/menu_forecast.js`
- CSS: `webpage/static/styles.css`
- Markup:
  - `data-popover`
  - `data-popover-trigger`
  - `data-popover-panel`
- Content mode: static HTML rendered with the page.
- Current timing:
  - hover visual open: 500ms
  - no lazy fetch
  - click: immediate pin/toggle
- Independent behavior:
  - trigger is a button.
  - panel contains current-menu and other-menu occurrence groups.
  - links open service context in a new tab for forecast history.

### Production Record History Variance

- Template: `webpage/templates/production_record_history.html`
- Controller today: `webpage/static/production_record_history.js`
- CSS: `webpage/static/styles.css`
- Markup:
  - `data-popover`
  - `data-popover-trigger`
  - `data-popover-panel`
- Content mode: static HTML rendered with the page.
- Current timing:
  - hover visual open: 500ms
  - no lazy fetch
  - click: immediate pin/toggle
- Independent behavior:
  - separate leftover and shortage popovers per variance row.
  - panel uses `production-record-variance-history-panel` width/layout class.

## Adjacent Overlays Not In First Refactor

These should remain outside the shared history popover controller for now:

- Inventory dialogs in `inventory.js`: native `<dialog>` open/close behavior.
- Menu forecast case overlay in `menu_forecast.js`: editable control surface, not hover history.
- Advanced unit overlay in `advanced_units.js`: form picker overlay.

## Slice Plan

### Slice 1: Extract Static Popover Controller

- Status: completed.
- Add `webpage/static/popover.js`.
- Move duplicated static popover governance out of `menu_forecast.js` and `production_record_history.js`.
- Keep existing attributes: `data-history-popover`, `data-history-trigger`, `data-history-panel`.
- Preserve 500ms hover open, click pin/toggle, outside click, and Escape behavior.
- Keep CSS hover governance: no immediate `:hover` reveal.
- Load `popover.js` from `base.html` before feature scripts.

### Slice 2: Move Inventory Lazy Fetch Governance Into Controller

- Status: completed.
- Extend `popover.js` to support optional lazy fetch:
  - fetch URL from markup
  - fetch delay from markup or default
  - loaded/loading state
  - fetch cancellation before request starts
- Keep inventory renderers in `inventory.js`.
- Register inventory renderers with the shared controller.
- Remove generic popover governance from `inventory.js`.
- Current defaults:
  - hover visual open: 500ms
  - hover fetch intent: 650ms
  - keyboard focus fetch: immediate
  - click on button trigger: immediate open and fetch
  - click on anchor trigger: preserve navigation

### Slice 3: Markup Normalization

- Status: completed.
- Add neutral aliases such as `data-popover`, `data-popover-trigger`, and `data-popover-panel`.
- Keep legacy `data-history-*` support during migration.
- Update one route at a time:
  - menu forecast
  - production record history
  - inventory dashboard
- Current templates now use neutral `data-popover*` attributes.
- `popover.js` still supports legacy `data-history-*` attributes for compatibility.

### Slice 4: CSS Naming Cleanup

- Status: completed.
- Introduce neutral classes such as `app-popover`, `app-popover-trigger`, and `app-popover-panel`.
- Keep old `menu-forecast-history*` classes as compatibility aliases until all templates migrate.
- Confirm CSS cannot bypass hover governance.
- Current templates and inventory-rendered lazy content now use neutral `app-popover*` classes.
- Legacy `menu-forecast-history*` CSS aliases remain for compatibility.

### Slice 5: Optional Lazy Static Popovers

- Evaluate whether menu forecast history or production record variance panels should also lazy-load if page size grows.
- Do not change content loading unless profiling shows the static panels are a material cost.

## Acceptance Checklist

- Inventory dashboard initial HTML stays near the optimized size, not the pre-lazy-load size.
- Fast mouse movement over inventory table does not issue popover API calls.
- Hovering for 500ms opens the panel.
- Inventory hover fetch starts after 650ms.
- Click opens/pins immediately.
- Outside click and Escape close open panels.
- Menu forecast history still works without feature-specific duplicated popover code.
- Production record variance history still works without feature-specific duplicated popover code.
