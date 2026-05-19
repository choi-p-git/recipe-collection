Recipe Collection System
Project Summary

The Recipe Collection System is a modular, database-driven application for managing recipes and base food submissions in a structured environment. It is designed as an MVP foundation for future menu planning, production, scaling, and nutrition-analysis workflows.

Current MVP behavior

- Recipes are structured records with batch yield, measurement data, ingredients, methods, and a primary cooking method.
- Base foods are lightweight approval submissions with only an item name and optional notes.
- A shared item detail page supports both recipes and base foods.
- Mock auth/login is session-backed for MVP development and role testing.
- A session-backed user preferences page stores display-mode and unit-system defaults per active mock user.
- Reviewer, dietitian, and admin workflow portals support status movement across the MVP lifecycle.
- Workflow history, note threads, and notifications are active across the review lifecycle.
- Dietitian-owned official serving fields are separated from submitter-facing recipe entry.
- Menu Builder, Forecasting, and Production Record workflows are active for live menu planning, production scaling, floor entry, posted review, CSV export, and print handoff.
- Advanced hotel-pan units are available only in live recipe scaling, forecasting, and future production-record workflows; recipe/base-food authoring remains limited to standard mass, volume, and count units.

System priorities

- Structured recipe data where structure matters
- Minimal friction for base food submission and approval
- Data integrity through validation and controlled inputs
- Expandability for future scaling, nutrition analysis, and external integration

Current implemented features

1. Database layer
SQLite migrations stored in `database/migrations/`
Latest full schema snapshot stored in `database/schema.sql`
Unified `item` table plus `recipe_component` table
Database initialization and pending migration application handled by `src/db.py`
Automatic seed catalog bootstrap on empty real databases:
- 1000 base foods
- 500 simple recipes
- 500 complex recipes

2. Mock auth shell
Session-backed mock login page
Existing account switcher
Direct mock user creation with role selection
Debug override panel for account, role, and display name testing
User Preferences page for session-backed display defaults

3. Base food workflow
Minimal base food submission form
Whitespace normalization and case-insensitive duplicate protection
Duplicate-name suggestion flow
Successful submit redirects to shared item detail page
Privileged edit flow now supports dietitian-owned base-food nutrition authority fields

4. Recipe workflow
Single-page multi-section recipe editor
Client-side validation with section warnings
Database-backed ingredient search
Shared live-only search stack with ranking, pagination, collection browsing, and fuzzy fallback
Recipe submit flow inserts item row and component rows
Recipe authorship follows the active mock session user
Instruction codec stores ordered method steps as numbered text
Recipe submit flow now captures yield mass and yield volume fields
Official serving fields are reserved for privileged dietitian/admin/super-user editing
When recipe yield unit is not `each`, the generic yield quantity is derived from the matching authoritative mass or volume basis instead of being user-entered directly
Recipe authoring unit fields deliberately exclude advanced hotel-pan units; backend validation rejects pan units for recipe yield, official recipe measurements, serving fields, and ingredient component rows

5. Item viewing
Shared item detail route at `/items/<item_id>`
Legacy recipe route redirects to the shared item detail route
Recipe pages render yield, ingredients, methods, cooking method, and classifications
Base food pages render only relevant information

6. My Recipes and testing
`/my-recipes` is scoped to the active mock session user and supports filtering/sorting
Automated tests cover schema initialization, services, policies, queries, routes, workflow, notifications, and instruction codec behavior

7. Workflow tooling
Reviewer portal for `submitted`, `reviewed`, and `analyzed` items
Dietitian portal for `approved` items
Admin workflow portal with full visibility and transition access
Official terminal `rejected` workflow status
Returned-to-submitter recipe flow with resubmission unlock
Workflow note threads hidden on `live` item detail pages
Workflow history timeline with reason capture on send-back and reject actions
Automatic workflow-action notifications for affected users/roles even without a note
Post-live item edits notify recipe authors plus reviewer and dietitian roles

Database migration/versioning note

- Add future schema changes as a new numbered SQL file in `database/migrations/`
- Keep migration filenames ordered, for example `0002_add_workflow_event.sql`
- `src/db.py` applies pending migrations and records them in the `schema_migration` table
- `src/db.py` also loads the built-in seed catalog when the database is empty
- `database/schema.sql` remains the latest full snapshot for rebuild/reference use
- Existing local databases without migration history are stamped forward the first time the migration runner sees them

Seed catalog note

- Empty real databases bootstrap with a reusable seed catalog stored in `src/seed_catalog.py`
- The seed catalog includes:
  - 1000 base foods, preserving the original named starter items and expanding with USDA-backed references when available
  - 500 simple recipes that use only base foods
  - 500 complex recipes that use both base foods and sub-recipes
- Seeded base foods now also include starter nutrition authority values for calories and serving reference mass/volume
- The loader is idempotent and only runs when the `item` table is empty
- Existing seed rows can be backfilled with newer seed nutrition metadata during init without touching non-seed records
- Tests use `initialize_database(seed=False)` so isolated DB fixtures stay clean unless a test explicitly wants seeded data

Search stack note

- Search results are limited to `live` items only
- Search behavior is shared so future modules such as Menu Builder or Inventory can reuse the same ranking and filtering path
- Current search stack supports exact match, prefix match, substring match, paged loading, collection browsing, and fuzzy fallback
- Very short fuzzy fallbacks stay strict by default and only relax after an initial zero-result response in the recipe editor picker

Menu Builder foundation note

- Menu Builder is now planned as a separate planning shell layered on top of the existing item, search, scaling, and preference services
- The current draft direction uses a `menu` -> `menu_slot` -> `menu_slot_item` model so one slot can contain multiple ordered recipes/base foods
- Current schema draft keeps menu-level day/meal/concept selections on the `menu` record and uses explicit `menu_slot` rows plus ordered `menu_slot_item` rows for overview rendering and assignment actions
- The first implemented Menu Builder slice now includes migration-backed `menu`/`menu_slot`/`menu_slot_item` tables plus a create-menu flow that materializes slots up front and redirects into a week-based overview shell
- The next implemented slice now supports first-pass slot assignment for `live` recipes and base foods, with slot cells linking into an assignment shell and the overview reflecting current assigned items
- Concept order is now treated as a menu-level layout contract: the stored concept list order drives overview rendering now and should later drive print/export sequence too
- Menu overview action selection can open Forecasting directly in a new browser tab
- Forecasting renders a 4-week cycle selector, search/filter/sort controls, and default recipe ordering by the menu configuration contract
- Forecasting scale-by-yield fields autosave with a 500ms debounce, saved-state feedback, and an unload warning when sync is pending or failed
- Forecasting now supports persisted per-assignment production batch splits. Users can enter a batch split as either a percent of the assignment forecast or as a target quantity, and the other value is calculated from the assignment forecast yield.
- Forecast production summary rollups combine same-recipe assignments and aggregate matching batch sequence totals across concepts so production can see the combined amount to prepare for each batch.
- Forecast production summary refreshes automatically after forecast or batch autosaves without reloading the editable forecast grid.
- Batch split rows include an optional planned time field as a foundation for later production timing and rush/shift scheduling.
- Forecasting now supports a first-pass `case` mode for recipes and base foods. Users enter case quantity, pack quantity, subunit size, and subunit unit; the visible forecast remains `case` while the calculated production yield is stored separately for batch and rollup math.
- Advanced case mode can link the case pack to one recipe ingredient, allowing recipe-yield and user-serving calculations to stay available when the ingredient basis can be converted back to recipe yield.
- Forecast, menu overview, and slot assignment item names link to item detail pages. Forecasted recipes open with the saved scale and user-serving values applied so the recipe view matches the production target.
- Menu Builder now has dedicated print views for week and day planning. Week print uses the selected overview week; day print defaults to the current service day when appropriate and otherwise the first service day of the selected week.
- Production Record is implemented as the first operational floor workflow after Forecasting. It snapshots the forecast for the selected menu week/day, supports actual production and end-of-service leftover/shortage entry, calculates implied demand and forecast accuracy, and captures reason codes plus notes.
- Production Record quantity fields support simple formula entry for floor-count math. Complete formulas save the calculated result while preserving the original formula for refocus/editing; incomplete but allowed formulas save as draft text until the user finishes the expression.
- Production Record can be posted and locked, reviewed from a posted record view, exported to CSV, and printed as a kitchen floor sheet.
- Recipe print is implemented as a single kitchen production sheet. It respects the active scaled target when present, always prints flattened ingredients, follows the selected display mode/unit system, and visually groups sub-recipe ingredients under their parent sub-recipes.
- Drag-and-drop, rules checks, richer batch timing workflows, production-record analytics, and inventory-facing rollups remain deferred until the current operational loop is refined.

Production Record refinement roadmap

- Current data flow: Menu Builder assignment -> Forecasting scale/display/case planning -> Production Summary rollup -> Production Record snapshot -> line-level actual production and end-of-service variance -> implied demand and forecast accuracy -> posted review, print, and CSV export.
- Current operational workflow: menu owner opens the current service day, optionally prints a kitchen floor sheet, cooks/managers record actual production and leftover/shortage, reason/notes capture operating context, then the manager posts the record to lock it for future review.
- Next refinement slice should add a Production Record history/index page per menu. It should show draft and posted records by date, week, and day, with quick links back to entry/review.
- Next reporting slice should add simple filters and summaries for date range, accuracy level, reason code, item, and posted/draft status. The first aggregate view should focus on count of accurate/review/miss records, top reason codes, and leftover/shortage trends.
- Future inventory tie-in should consume posted Production Record and Forecasting data rather than draft records. Forecasting should drive expected demand/order needs; posted Production Records should feed actual usage, leftover/shortage, and variance signals.
- Inventory pack/case definitions should be item-linked, not recipe-linked, and should reuse saved pack sizes where possible. Forecast-linked case sizes can remain local to a menu cell until explicitly saved to the item-level pack library.
- Future inventory availability should attach to ingredient/base-food item IDs and later offer live system matches, available quantity, case size, and ordering status back into Forecasting and Production Record views.

Scaling foundation note

- Sub-recipes can already be flattened at render time for `live` recipes in a first-pass read-only view
- Unit compatibility is moving into a dedicated scaling foundation layer instead of editor-side enforcement
- Approved units now serve as the basis for future mass / volume / count awareness and later conversion services
- Same-unit sub-recipe scaling is ratio-ready today, and same-family unit conversion is now modeled through a shared conversion service
- Recipes now carry mass and volume measurement fields that are required by the main recipe editor flow and required before a recipe can go live
- Base foods keep a default serving count of `1`, with official mass/volume basis data managed through privileged edit flow
- Base foods now also support privileged nutrition authority fields such as nutrition group, calories per serving, and serving reference mass/volume
- Live recipe detail pages now support same-family target scaling by requested batch quantity/unit
- Live recipe detail pages now support recipe-level mass<->volume bridge scaling using the recipe's own authoritative mass and volume fields
- Recipes with `yield_unit = each` can still scale to mass or volume targets by anchoring the scale factor through the recipe's official batch mass or batch volume
- The shared conversion layer now also defines base-food mass<->volume bridge conversion using a base food's official mass and volume fields for future module reuse
- Scaling currently supports hierarchical and flattened output modes with warning-based fallback for unsupported target units
- Advanced ingredient scaling is available on live recipe detail pages, including bottom-up scaling from a selected ingredient in hierarchical or flattened views
- Forecast-launched scaling can confirm the scaled recipe yield back to the Forecasting page, preserving the selected target unit where possible
- Advanced hotel-pan volume units are modeled as canonical conversion units for live scaling and forecasting, with pan size/depth UI controls and internal ml conversion factors
- Advanced hotel-pan units are intentionally excluded from recipe/base-food authoring controls and service-layer authoring validation
- Richer scaled recipe rendering now preserves original ingredient units while also surfacing official mass/volume equivalents when the scaling target is measurement-aware and the ingredient or sub-recipe has authoritative bridge data
- Once a recipe is scaled, recipe snapshot/yield fields render the scaled yield, mass, volume, and serving count while preserving serving size
- Live recipe detail pages now support display-mode toggles for `default`, `volume`, and `mass`, plus separate `imperial` / `metric` unit-system selection
- Volume and mass display modes use full unit-cascade rendering, choosing the largest logical unit that keeps the rendered quantity at or above `1` and stepping down to smaller units when needed
- Metric liter display uses `L`; legacy lowercase `l` values are normalized by migration and conversion helpers
- `each` components remain rendered in `each` across display modes so count-based items such as tortillas can still scale fractionally without forced mass/volume display
- Scaling Foundation and Audit panels are now hidden behind a privileged technical-details toggle on the item detail page
- Base-food nutrition authority metadata is also hidden behind the privileged technical-details toggle

MVP validation checklist

1. Run `.\.venv\Scripts\python.exe .\src\db.py`
2. Run `.\.venv\Scripts\python.exe -m pytest -q`
3. Verify base food create, detail view, and reviewer/dietitian/admin workflow movement
4. Verify recipe create, edit, return-to-submitter, resubmit, analyze, and live flow
5. Verify notes, automatic workflow notifications, and notification clearing on item view
6. Verify live item default view hides workflow notes/history, with advanced toggle for privileged roles
7. Verify Forecasting autosave, advanced scaling confirm-back, and hotel-pan unit availability only on live scaling/forecast controls
8. Verify Production Record current-day landing, formula entry, post/lock, review, CSV export, and kitchen floor print
9. Verify Menu Builder week/day print and Recipe production-sheet print, including scaled flattened sub-recipe grouping

Test temp housekeeping

- Isolated tests create temporary SQLite databases under `.test_tmp/run-*` and remove them after normal completion.
- If test runs are interrupted or Windows file locks prevent cleanup, stale run directories can accumulate.
- Preview cleanup with `.\.venv\Scripts\python.exe .\src\db.py --gc-test-tmp`
- Apply cleanup with `.\.venv\Scripts\python.exe .\src\db.py --gc-test-tmp --gc-apply`
- The collector only targets direct `.test_tmp/run-*` and `.test_tmp/debug-*` directories older than 24 hours by default. Use `--gc-min-age-hours 1` when you intentionally want a more aggressive cleanup window.

Schema Change Checklist

1. Add a new numbered SQL migration in `database/migrations/`
2. Put the schema/data change in that migration file
3. Update `database/schema.sql` so the snapshot matches the latest DB shape
4. Update app code, queries, services, templates, and tests as needed
5. Run `.\.venv\Scripts\python.exe .\src\db.py`
6. Run `.\.venv\Scripts\python.exe -m pytest -q`
7. Manually verify the affected workflow or UI behavior

Patch Notes

## v0.0.1

Initial MVP proof-of-concept release.

Highlights

- Added unified item support for both `recipe` and `base_food` records
- Added shared item detail pages with recipe-specific and base-food-specific rendering
- Added base food submission flow with duplicate-name handling and minimal approval-oriented fields
- Added multi-section recipe editor with validation, ingredient search, and structured submit/edit flow
- Added mock auth shell with account switching, role selection, and debug override support
- Added `My Recipes` view with filtering and sorting for the active mock user
- Added reviewer, dietitian, and admin workflow portals
- Added returned-to-submitter recipe flow with resubmission unlock for the original author
- Added workflow note threads, workflow history timeline, rationale capture for send-back/reject actions, and automatic notifications for workflow actions
- Added live-item advanced workflow toggle for privileged roles while keeping default live pages clean
- Added lightweight forward-only SQLite migration/versioning support through `database/migrations/`
- Added centralized role/policy service for workflow and item-level permissions
- Expanded automated validation coverage across schema, services, policies, queries, routes, workflow, notifications, and instruction codec behavior

## Current working milestone

The current proof-of-concept has a complete operational vertical stack:

- Menu Builder creates dated menu cycles, assigns ordered live items into service slots, supports bulk planning actions, and provides week/day print views.
- Forecasting scales menu assignments by yield, portions, cases, advanced hotel-pan units, and linked ingredient case packs.
- Production Summary rolls Forecasting data into production-facing totals.
- Production Record captures floor actuals, leftover/shortage, formula-based quantity entry, reason codes, notes, implied demand, forecast accuracy, post/lock, review, CSV export, and floor-sheet print.
- Recipe Detail supports scaled and flattened production views, display-mode/unit-system toggles, and a kitchen production-sheet print with sub-recipe grouping.

The next recommended development focus is Production Record history/reporting, followed by the first Inventory Management foundation.
