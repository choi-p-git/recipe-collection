# AGENTS.md - Recipe Collection System

## Project Purpose

A web-based Recipe Collection System for managing base foods and recipes with structured composition, workflow lifecycle, and future integration into a Menu Builder system.

This project is being built as a staged MVP with deliberate business-analysis-first design, followed by technical implementation.

## Current Architecture

* Backend: Python
* Web framework: Flask
* Database: SQLite
* SQL migrations stored under `database/migrations/`
* latest schema snapshot stored in `database/schema.sql`
* Frontend assets live under `webpage/`
* Core Python logic lives under `src/`
* reusable seed catalog bootstrap lives in `src/seed_catalog.py`
* dev operating-data automation lives in `src/dev_automation.py`

### Major Module / App Boundaries

Treat each first URL segment as the major module/app boundary for future architecture.

Current and planned examples:

* `/recipe-collection` represents the Recipe Collection app: recipe creation, base-food submission, live collection browsing, item detail, and related collection workflows
* `/menus` represents the Menu Builder app: menu cycles, slot assignment, Forecasting, Production Record, service context, and production history/reporting
* future `/inventory` should represent the Inventory app: current counts, count freshness, pack/case definitions, availability, and purchasing suggestions
* future `/analytics` should represent the Analytics app: trend, usage, menu, cost, portion-control, and forecast/purchasing recommendation analysis

Architectural guidance:

* Recipe Collection / recipe creation is its own app, not merely a setup screen for Menu Builder
* Menu Builder is its own app, not merely a feature inside Recipe Collection
* shared services such as item search, item detail, scaling, unit conversion, workflow policy, preferences, and auth may be reused across apps
* app-specific screens, routes, navigation, and future tests should keep clear ownership under their top-level module route
* app-owned APIs should use the same module prefix where practical, for example `/recipe-collection/api/...` for recipe/item APIs
* when adding a major feature, choose the top-level URL segment first and let templates/services follow that ownership boundary where practical

## Dev Automation Guidance

`src/dev_automation.py` is back-of-house tooling for creating manual-test operating data after the commercial kitchen seed catalog is in place.

Current default shape:

* 8 weeks
* Monday-Friday
* breakfast and dinner
* hot line, cold line, and grab go
* 3-5 randomized live recipes/base foods per slot
* draft Forecasting rows for every assignment
* draft Production Records with randomized accurate/review/miss scenarios

Keep generated records draft by default. Posting should stay opt-in through the `--post-records` flag so manual testing can exercise editable workflows before lock/post behavior. Future inventory/analytics automation should build on the same menu/forecast/production services instead of inserting downstream records directly.

## Current Folder Structure

* `database/`

  * `migrations/`
  * `schema.sql`
  * `recipe_collection.db`
* `src/`

  * `app.py`
  * `db.py`
  * `config/`
  * `services/`
  * `queries/`
* `webpage/`

  * `templates/`
  * `static/`
* `tests/`

## Core Business Model

### Item

A master record representing a usable food object.

MVP item types:

* `base_food`
* `recipe`

### Base Food

A single atomic item entry used as-is inside recipes.

* cannot own component rows
* does not require instructions
* does not require primary cooking method
* does not require yield or serving fields in MVP
* current web submission captures only item name plus optional notes
* uses shared system author identity in DB for consistency

Examples:

* granulated garlic
* granulated sugar
* spinach
* romaine lettuce
* shredded carrots
* strawberry preserve
* liquid egg
* assorted crackers
* pepperoni
* honey ham

### Recipe

A composed item entry that:

* requires instructions
* requires one primary cooking method
* contains one or more structured components
* may contain base foods, sub-recipes, or both
* stores original author identity from web app layer

### RecipeComponent

A child record linking a parent recipe item to another item.
Each row means:

* parent recipe uses component item in quantity + unit

This enables nested recipes.

## Locked MVP Business Rules

### Naming

* `item_name` must be globally unique
* uniqueness is case-insensitive
* input names are normalized for whitespace:

  * trim leading/trailing whitespace
  * collapse repeated internal whitespace to a single space
* duplicate-name suggestions follow the pattern:

  * `Name`
  * `Name (1)`
  * `Name (2)`
* current numbering rule: highest existing suffix + 1

### Item Type Rules

* each item must be either `base_food` or `recipe`
* only recipes may own component rows
* base foods are atomic within MVP
* recipe components may reference either base foods or recipes

### Recipe Rules

* recipes require:

  * `instructions_text`
  * `primary_cooking_method_code`
  * one or more components
* base foods do not require:

  * instructions
  * cooking method

### Yield and Serving Rules

* recipes require `yield_quantity`
* recipe `yield_quantity` must be > 0
* recipes require `yield_unit`
* base foods do not require yield fields in MVP
* recipe submitter-facing serving fields are removed from the main recipe entry flow
* official serving fields are dietitian-owned and may be edited by dietitian/admin/super user roles
* serving values must be > 0 if present
* base foods default to serving count `1` for future scaling compatibility

### Workflow Rules

Allowed statuses:

* `submitted`
* `reviewed`
* `approved`
* `analyzed`
* `live`
* `rejected`

Workflow progression is strict:

* `submitted -> reviewed -> approved -> analyzed -> live`

Other workflow rules:

* web-created items default to `submitted`
* CLI-created items require manual status entry
* submitter cannot edit after submission unless item is returned for revision
* no separate returned-for-revision status in MVP
* when returned for revision, visible status reverts to `submitted`
* unsaved revision edits are session-only and discarded if user leaves before resubmitting
* `rejected` is a terminal global workflow status
* dietitian send-back returns an item to `reviewed`
* recipes cannot go `live` without both mass and volume measurement data present

### Time Rules

* `created_at` is set on first submission and never changes
* `updated_at` refreshes when item content changes or workflow stage changes

### Author Rules

* recipes store real author identity
* author maps to authenticated web app values:

  * `author_user_id`
  * `author_display_name`
* base foods do not have a unique business author
* for DB/query consistency, base foods use a shared system identity

### Visibility Rules

* all `live` recipes should be visible to all users
* `live` item detail pages should hide workflow-note and workflow-history sections by default
* reviewer, dietitian, admin, and super user roles may explicitly enable advanced workflow view on live items
* `My Recipes` is a personal recipe submission archive for the current user
* base foods are shared system records, not personal-authored records

## Locked Controlled Lists

### Item Type

* `base_food`
* `recipe`

### Status

* `submitted`
* `reviewed`
* `approved`
* `analyzed`
* `live`

### Cooking Methods

Stored in DB as normalized string codes.
Current approved list:

* `air_fry`
* `combi_oven`
* `no_cooking`
* `bake`
* `barbecue`
* `blanch`
* `braise`
* `boil`
* `brown`
* `caramelize`
* `charbroil`
* `fry`
* `griddle`
* `grill`
* `pan_sear`
* `par_boil`
* `reduce`
* `roast`
* `saute`
* `simmer`
* `smoke`
* `steam`
* `stew`
* `stir_fry`
* `sweat`

MVP governance:

* controlled list for standard users
* future admin/super-users may extend list

### Units

MVP units are controlled string values selected from dropdowns in the web app.
Stored as text in DB.

Current unit governance:

* standard authoring units are available in recipe/base-food create and edit flows
* advanced hotel-pan volume units are canonical conversion units reserved for live recipe scaling, Forecasting, and future production-record workflows
* advanced hotel-pan units must not be accepted for recipe component units, recipe authoring yield units, recipe authoring measurement authority fields, or base-food authority fields

## Current Database Design

### Tables

#### `schema_migration`

Stores applied SQL migration filenames.

Key fields include:

* `version`
* `applied_at`

#### `item`

Stores both base foods and recipes.

Key fields include:

* `item_id`
* `item_name`
* `item_type`
* `author_user_id`
* `author_display_name`
* `yield_quantity`
* `yield_unit`
* `mass_quantity`
* `mass_unit`
* `volume_quantity`
* `volume_unit`
* `serving_size_quantity`
* `serving_size_unit`
* `serving_count`
* `instructions_text`
* `primary_cooking_method_code`
* `status`
* `requires_resubmission`
* `notes`
* placeholder classification fields
* `created_at`
* `updated_at`

#### `recipe_component`

Stores recipe composition rows.

Key fields include:

* `recipe_component_id`
* `parent_recipe_item_id`
* `component_item_id`
* `component_quantity`
* `component_unit`
* `component_sequence`
* `component_notes`

### Key relational design principle

`recipe_component` references `item` twice:

* once as parent recipe
* once as component item

This is what enables nested recipes.

## Current Implemented MVP Features

### Mock Auth Shell

Implemented:

* session-backed mock login page
* existing account selection
* direct mock user creation with role selection
* debug override panel for account, role, and display name
* user preferences page for session-backed display defaults
* current recipe authorship follows the active mock session user
* `My Recipes` uses the active mock session user for filtering
* display-mode and unit-system defaults are stored per active mock user and used as the default live recipe detail view unless a page-level override is present

### Database Bootstrap Seed Catalog

Implemented:

* empty real databases auto-load a reusable seed catalog
* seed catalog currently includes:

  * 500 commercial-kitchen base foods
  * 100 simple recipes using only base foods
  * 100 complex recipes using both base foods and recipes

* seed loading is idempotent and only runs when the `item` table is empty
* seed base foods should favor common commercial-kitchen ingredient names over raw USDA/nutrition-database names
* USDA-backed rows are allowed as fallback/reference inputs only after name normalization and exclusion of non-kitchen items such as infant formula, supplements, medical foods, alcohol, restaurant prepared meals, and similar noise
* seeded base foods now include starter nutrition authority values for calories and serving reference mass/volume
* init may backfill newer nutrition authority seed metadata onto older seed base foods without touching non-seed records
* isolated test databases should continue using `initialize_database(seed=False)` unless a test explicitly needs seeded data

### Workflow Tooling

Implemented:

* reviewer portal for `submitted`, `reviewed`, and `analyzed` items
* dietitian portal for `approved` items
* admin workflow portal with full visibility
* role-based workflow transitions
* terminal `rejected` status
* send-back from dietitian to `reviewed`
* reviewer return-to-submitter flow for submitted recipes
* submitter resubmission unlock via `requires_resubmission`
* workflow history timeline on item detail pages
* required rationale capture for send-back and rejection actions
* note threads plus auto workflow-action notifications
* workflow notes and history hidden by default once an item is `live`
* advanced workflow toggle for reviewer, dietitian, admin, and super user roles on live items
* post-live item edits notify the recipe author plus reviewer/dietitian roles, excluding admin

### Base Food Flow

Implemented:

* New Base Food form
* normalization of item name whitespace
* case-insensitive duplicate protection
* duplicate-name suggestion
* empty-name guard
* minimal submission fields: item name + optional notes
* DB insert through service layer
* friendly validation messages
* privileged edit flow supports official mass/volume plus nutrition authority metadata

### Recipe Editor Shell

Implemented as a single-page multi-section editor with frontend section switching.

Current sections:

* General Information
* Ingredients
* Methods
* Classification
* Finish

Current editor behavior:

* session-only in-memory page state
* no autosave
* no persistent draft record
* per-page validation
* warning icons by section
* submit button disabled until required sections are valid

### Ingredients Editor

Implemented:

* one row by default
* Add Ingredient button
* Move Up / Move Down
* delete row
* selected item stored via hidden item ID field
* debounced DB-backed search
* dropdown-style attached result panel under input
* click-to-select result

Current search behavior:

* DB-backed
* attached results panel
* actual selected item ID required for validation
* `live` items only
* offset-based pagination / scroll loading
* broader live collection search page
* fuzzy fallback available after exact/prefix/substring matching
* shared search path should remain reusable for future Menu Builder / Inventory modules

### Methods Editor

Implemented:

* one step row by default
* Add Step button
* Move Up / Move Down
* delete row
* one primary cooking method select

### Recipe Instruction Codec

Implemented as a swappable translation layer.

Current design:

* UI works with ordered step strings
* codec builds a neutral instruction model
* neutral model is encoded into plain text for DB storage
* plain text can be decoded back into ordered steps

Current storage format:

* numbered plain text in `instructions_text`

Reason for current choice:

* simple MVP storage
* easy manual DB inspection
* easy debugging
* swappable later to structured JSON or richer model

### Recipe Submit Flow

Implemented end-to-end:

* frontend collects editor payload
* sends JSON to Flask route
* backend validates recipe payload
* backend encodes methods into `instructions_text`
* backend inserts recipe into `item`
* backend inserts components into `recipe_component`

### Item Detail Page

Implemented as a shared route and render page:

* `/recipe-collection/items/<item_id>`
* legacy `/items/<item_id>` and `/recipes/<recipe_id>` redirect to the shared Recipe Collection item route

Current detail page renders:

* item name
* item ID
* author
* status
* notes
* created/updated timestamps
* recipe-only sections for yield, cooking method, ingredients, methods, and classifications
* base food detail view without recipe-only sections

## Current UI/UX Decisions

### Recipe Editor Architecture

* single Flask page
* section switching handled client-side
* not implemented as multi-route wizard

### Validation UX

* per-section warning icons
* Finish page summary
* disabled submit button until valid

### Current temporary dev behavior removed

* popup success alerts were used temporarily during dev
* successful submissions now route to the shared item detail page instead

## Search Design Notes

Current implementation is lightweight and suitable for MVP/local use.

Locked future design direction:

* debounce target: `150ms`
* minimum search length: `2 characters`
* initial result display limit: `15`
* later support scroll/pagination for more results
* indexing remains important for performance

## Post-MVP Roadmap

### 1. Recipe Viewing / Rendering Enhancements

* richer rendered recipe page
* cleaner styled recipe layout
* continue improving non-recipe/base-food detail presentation
* preserve current shared item-detail route while improving presentation

### 2. Menu Builder / Forecasting / Production Integration

Current state:

* live recipes and base foods are available for selection in Menu Builder
* Menu Builder supports dated menu cycles, service-day grids, ordered slot assignments, bulk copy/paste/clear actions, and dedicated week/day print views
* Forecasting supports assignment-level scaling, user-serving targets, case mode, saved item case packs, advanced hotel-pan display, production batch splits, and production summary rollups
* Production Record is active as the operational floor workflow after Forecasting
* Recipe print is active as a single kitchen production sheet using the active scaled target, flattened ingredients, display preferences, and sub-recipe grouping

### 2A. Menu Builder Spec v0.1

Locked current direction:

* Menu Builder should be treated as a separate planning shell built on top of Recipe Collection cores
* it should reuse:

  * shared live-item search
  * shared scaling / conversion services
  * shared user preferences
  * shared item-detail and measurement authority concepts

* a unified platform preferences shell should eventually house:

  * global display preferences
  * Menu Builder preferences
  * future default scaling behavior
  * future service-specific preferences

* Menu Builder needs three core business objects:

  * `menu`
  * `menu_slot`
  * `menu_slot_item`

* a `menu_slot` represents one schedulable location defined by:

  * menu
  * week
  * day of service
  * meal period
  * concept / line

* one slot may contain multiple assigned items
* assigned items inside a slot should be ordered and future-ready for rearrangement
* concepts represent the product name of a line / station and are not recipe restriction rules
* v0.1 slot assignment should allow both:

  * `recipe`
  * `base_food`

* future `customizable` item type should later become available in Menu Builder once it exists in Recipe Collection
* first Menu Builder create flow should capture:

  * service-day toggles (`Sunday` through `Saturday`)
  * meal-period toggles (`breakfast`, `lunch`, `dinner`)
  * concept toggles
  * menu length in weeks
  * confirmation / save step

* first Menu Builder overview shell should support:

  * week switcher
  * overview grid by week/day/meal/concept
  * clickable slot cells
  * visible assigned items inside each slot

* first assignment shell should use:

  * left-side live-item search
  * right-side pending assignment context
  * confirm / cancel actions

* drag-and-drop is deferred to a later release, but slot item ordering should remain drag-ready
* first copy / paste scope should be limited to item assignments only
* first utility actions should support:

  * clear slot
  * copy / paste slot assignments
  * copy / paste day assignments
  * copy / paste week assignments

* slot-level scaling persistence is deferred in the first version
* scaling behavior should remain governed by user preferences rather than initial slot data
* bottom-up scaling is a required future Menu Builder capability:

  * user selects one specific item from a flattened list
  * user enters target quantity / unit for that item
  * system solves backward for the parent recipe scale factor

* bottom-up scaling belongs in the shared scaling service layer, not only in Menu Builder UI
* current Menu Builder / Forecasting / Production stack still defers:

  * drag-and-drop
  * rules engine / conditional checks
  * slot-level scaling overrides
  * nutrition balancing
  * inventory rollups and ordering calculations

* rules checks and conditional checks should be implemented only after base Menu Builder object behavior is stable

### 2C. Production Record Current State

Current data flow:

* Menu Builder assigns live items to date-aware service slots
* Forecasting stores scaled production targets per assignment
* Production Summary rolls assignment forecasts into item-level production requirements
* Production Record snapshots the selected week/day production summary into record lines
* Users enter actual production and end-of-service leftover/shortage by line
* The service calculates implied demand and forecast accuracy from actual production minus leftover/shortage
* Users select a reason code and may add reason notes or line notes
* Posting locks the record and preserves it for review, print, CSV export, and future analysis

Current operational workflow:

* the production user lands on the current service day by default
* a manager or lead can print a kitchen floor sheet before service
* cooks/managers can enter actual production, leftover/shortage, reason, and notes digitally
* quantity fields accept simple math formulas for live count totals
* incomplete formula drafts are preserved while typing and do not count as completed quantities
* posted records are locked from editing and reviewed from a separate posted view

Important current semantics:

* `end_service_variance_quantity` represents end-of-service leftover or shortage from actual production
* positive variance means leftover food
* negative variance means under-production against demand
* implied demand is calculated as `actual production - end service variance`
* forecast accuracy is calculated against implied demand, not raw actual production
* reason codes are available even when the record is within the accurate range
* posted records expose `production_record.posted_facts.v1` at `/api/menus/<menu_id>/production-record/posted-facts`
* posted facts are the current source-of-truth contract for Inventory and Analytics; drafts are intentionally excluded
* posted fact split fields keep downstream consumers simple:

  * `actual_production_quantity` / `actual_production_unit` = floor-entered production amount
  * signed `end_service_variance_quantity` / `end_service_variance_unit` = leftover if positive, shortage if negative
  * `leftover_quantity` and `shortage_quantity` = non-negative split of end-service variance
  * `implied_demand_quantity` / `implied_demand_unit` = actual production minus signed variance
  * `forecast_error_quantity`, `forecast_error_percent`, and `forecast_accuracy_level` = forecast performance against implied demand

### 2D. Production Record Refinement Roadmap

Implemented refinement slices:

* Forecasting occurrence history panel per forecast row / item
* support for both `recipe` and `base_food` items
* grouped occurrences into:

  * current menu occurrences
  * other menu occurrences

* includes posted records and draft/current in-progress records when production fields have been filled
* same-menu occurrence history includes only past service dates with filled Production Records
* occurrence rows show:

  * service date
  * menu name
  * week/day
  * meal period and concept context
  * forecast quantity/unit
  * actual production quantity/unit
  * end-of-service leftover/shortage quantity/unit
  * implied demand quantity/unit
  * forecast error / accuracy percent
  * reason code label
  * notes indicator

* occurrence dates link to the combined service context view for the selected date
* combined context view shows the selected service date's Forecasting context and Production Record context together
* Production Record index/history page scoped to a menu
* history page lists draft and posted records by service date, week, and day
* history page exposes quick actions:

  * continue draft entry
  * review posted record
  * export CSV for posted record
  * open combined service context

Current operational/reporting slice:

* default Production Record landing should still favor the current service day
* history views should make past posted and draft records easy to retrieve without rebuilding a forecast context manually
* filtering and lightweight reporting are implemented on top of the existing Production Record history data
* algorithmic suggested forecast should be deferred until the occurrence/history/reporting UI is stable
* future suggested forecast should use historical implied demand as the primary early signal
* future algorithm inputs may include menu mix, attendance, weather, field trips, sports/team away days, seasonality, and service-day patterns

Implemented reporting slice:

* filters for:

  * date range
  * week/day
  * item
  * reason code
  * accuracy level
  * draft/posted status

* aggregate summaries for:

  * accurate / review / miss counts
  * top reason codes
  * leftover quantities by item
  * shortage quantities by item

Future reporting slice:

* add forecast error trend by item over time
* add posted-only default views for analytics-oriented reporting while keeping draft inclusion explicit

Implementation guidance:

* Forecasting occurrence history may show posted and draft/current filled records because managers need operational memory while forecasting
* reporting and corporate analytics should prefer posted Production Records by default, with explicit filters if draft records are included
* Inventory and Analytics integrations should consume `production_record.posted_facts.v1` before reading production tables directly
* keep report calculations in a service/query layer instead of templates
* preserve formula text separately from calculated numeric values
* keep reason-code values stable because future analytics and inventory/waste workflows will depend on them
* occurrence lookup should be implemented as a read-only query/service first; avoid introducing algorithm tables until the UI behavior is validated

### 2E. Future Inventory Tie-In Plan

Inventory should build on the current Menu Builder / Forecasting / Production data path:

* Inventory app should become the source for current inventory count records and count freshness
* Forecasting provides expected demand and order-planning quantities
* Production Record provides actual usage, leftover, shortage, and forecast miss signals
* posted Production Records should feed historical demand and variance analysis
* Forecasting and Production Record should eventually have API access to inventory availability, item counts, case sizes, and purchasing status
* inventory should attach to item IDs, especially base-food ingredient IDs
* reusable pack/case definitions should attach to item IDs, not recipes
* menu-cell-local case sizes may exist for forecast work, but saving a reusable pack size should explicitly write an item-level pack definition
* future live inventory feeds should match an inventory line to an item ID and case-size definition
* inventory availability can later surface back into Forecasting as:

  * available on hand
  * expected shortage
  * suggested order quantity
  * case/pack order count
  * live price or estimated cost when pricing data exists

Future analytics tie-in:

* inventory estimated-vs-actual usage should feed portion-control and usage-accuracy analytics
* analytics should consume usage, menu, purchasing, cost, variance, and inventory history
* future algorithm work may estimate year-over-year trends and suggest production or purchasing adjustments to prevent over/under production and purchasing
* keep analytics algorithms out of the inventory foundation until the underlying record contracts are stable

Deferred inventory work:

* live vendor or inventory-system integrations
* order guide generation
* food-cost projection
* food-waste app handoff beyond preserving positive Production Record variance as future leftover-food input

### 2B. Menu Builder Schema Draft v0.1

Recommended first schema shape:

#### `menu`

Purpose:

* top-level planning object for one menu build

Required fields:

* `menu_id`
* `menu_name`
* `author_user_id`
* `author_display_name`
* `service_days_json`
* `meal_periods_json`
* `concepts_json`
* `menu_length_weeks`
* `status`
* `created_at`
* `updated_at`

Recommended rules:

* `menu_name` is required
* `menu_length_weeks` must be `> 0`
* `service_days_json` stores selected days from:

  * `sunday`
  * `monday`
  * `tuesday`
  * `wednesday`
  * `thursday`
  * `friday`
  * `saturday`

* `meal_periods_json` stores selected meal periods from:

  * `breakfast`
  * `lunch`
  * `dinner`

* `concepts_json` stores the selected concept/line names in current display order
* first status set can remain lightweight, for example:

  * `draft`
  * `active`
  * `archived`

Reasoning:

* JSON lists are acceptable in v0.1 because selected days, meal periods, and concepts are menu-level configuration state rather than cross-menu relational data
* concept order matters for overview rendering, so preserving concept list order at the menu level is useful
* concept order is a menu-level layout contract:

  * it drives overview render sequence
  * it should later drive print / export sequence
  * reordering concepts changes display order only and does not change slot identity or assigned items
  * concept-targeted operations continue to match by `concept_name`, not by row position

#### `menu_slot`

Purpose:

* one schedulable slot in the overview grid

Required fields:

* `menu_slot_id`
* `menu_id`
* `week_number`
* `day_of_week`
* `meal_period`
* `concept_name`
* `created_at`
* `updated_at`

Recommended uniqueness:

* unique on:

  * `menu_id`
  * `week_number`
  * `day_of_week`
  * `meal_period`
  * `concept_name`

Recommended rules:

* `week_number` must be `>= 1`
* `day_of_week` must be one of the controlled day values
* `meal_period` must be one of the controlled meal values
* `concept_name` is required and should match one of the menu's configured concepts at the application layer

Reasoning:

* explicit slot rows make the overview grid addressable for copy/paste/clear actions
* a slot should exist even when no items are assigned yet

#### `menu_slot_item`

Purpose:

* ordered item assignment inside a slot

Required fields:

* `menu_slot_item_id`
* `menu_slot_id`
* `item_id`
* `item_sequence`
* `created_at`
* `updated_at`

Recommended rules:

* `item_id` references `item(item_id)`
* application layer should restrict first-release assignments to `live` items only
* application layer should allow first-release assignment for:

  * `recipe`
  * `base_food`

* `item_sequence` must be `>= 1`

Recommended uniqueness:

* unique on:

  * `menu_slot_id`
  * `item_sequence`

Reasoning:

* ordered slot rows support future rearrangement without changing the slot identity
* copy/paste of assignments can be implemented by duplicating `menu_slot_item` rows only

Explicitly deferred from first schema:

* slot-level scaling overrides
* slot-level notes
* slot-level rule-check results
* drag-and-drop metadata
* menu publication workflow
* inventory rollup state
* nutrition rollup state
* bottom-up scaling target storage

Recommended implementation path:

1. add `menu`, `menu_slot`, and `menu_slot_item`
2. build create-menu flow that materializes slot rows at menu creation time
3. build overview grid from `menu_slot`
4. build slot assignment flow on top of `menu_slot_item`
5. add copy/paste/clear actions at the service layer before introducing richer menu rules

Current implementation status:

* migration-backed `menu`, `menu_slot`, and `menu_slot_item` tables are now in place
* first create-menu flow is implemented
* menu creation now materializes slot rows up front based on:

  * selected service days
  * selected meal periods
  * selected concepts
  * selected menu length in weeks

* first menu detail route now renders a week-based overview shell with slot placeholders ready for future assignment flow
* first slot assignment flow is now implemented for `live` recipes and `live` base foods
* slot cells now expose assignment links and render currently assigned item names in overview

### 3. Customizable Item Type

Planned future item type:

* `customizable`

Purpose:

* user-selectable collection of recipes and base foods
* example: salad bar using romaine lettuce and chicken salad

Not in MVP.

### 4. Instructions Model Expansion

Current MVP stores plain text via codec.
Future options:

* grouped instruction sections
* richer neutral instruction model
* JSON-backed storage model or secondary structured field
* prettify algorithm for temperatures and formatting

Grouped methods are post-MVP.
Prettify algorithm is post-MVP.

### 5. Scaling Enhancements

Current MVP uses simplified yield model:

* one yield quantity/unit
* optional serving fields

Post-MVP requirement:

* mass yield
* volume yield
* user-defined serving size changes
* scale by serving size
* scale by yield using approved unit list
* mass-to-volume conversion
* unconventional operational scaling such as hotel pans

### 5A. Sub-Recipe Flattening and Scaling Spec v0.1

Locked direction for the first post-MVP implementation slice:

* flattening is read-only and render-time only in the first implementation
* flattening is available for `live` recipes only
* users should be able to toggle between hierarchical and flattened ingredient views
* first scaling target is recipe yield
* future scaling must eventually support:

  * mass
  * volume
  * mass-to-volume
  * volume-to-mass
  * unconventional operational units
  * user-defined portion scaling
  * dietitian-defined portion scaling

* submitted portion-related values are provisional
* operational hotel-pan units are scaling/forecast units, not recipe authoring units
* final analyzed/live recipe should eventually store official dietitian-defined portion fields
* user-defined portion calculation will live in a separate later service layer
* first flattening pass preserves original units rather than converting units
* child recipe expansion uses ratio math:

  * parent requested child quantity divided by child recipe yield quantity

* first flattening pass only fully expands child recipes when same-unit ratio math is directly available
* same-family unit conversion should be handled by a dedicated shared conversion service
* conversion-aware flattening beyond same-family support remains deferred until broader conversion logic exists
* quantities that round below `0.001` should render as `according to taste`
* indirect recipe-cycle detection should exist
* cycle detection should surface warnings in rendering rather than hard-stopping the user-facing page
* flattened render should preserve the original parent recipe component order
* flattened sub-recipes should render as their own visible sub-tree block inside that parent order
* ingredients inside each flattened sub-recipe should preserve their original component order
* shared ingredients across parent and child branches must remain separate rows in flattened view and must not be merged
* future unit-conversion work should likely introduce:

  * explicit mass / volume awareness on units
  * mathematical relationships between approved units
  * likely density-aware base food data
  * recipe-level mass yield and volume yield
* do not enforce sub-recipe selected units in the editor based on child recipe yield unit
* unit compatibility belongs to the future measurement / conversion service layer

### 5B. Scaling Foundation Layer

Current post-MVP foundation direction:

* approved units now conceptually map to measurement types:

  * mass
  * volume
  * count

* scaling foundation should classify units even before conversion is fully enabled
* same-unit child recipe calls are direct-ratio ready
* same-measurement-type child recipe calls should use the shared same-family conversion service
* cross-measurement-type relationships should be recognized as incompatible until richer conversion logic exists
* flattening may still skip non-direct conversions until flattening is explicitly upgraded to apply shared conversion results
* dietitian-defined official portion fields remain a later schema/model step

### 5C. Conversion Model Spec v0.1

Locked direction for the first conversion implementation:

* unit conversion must be centralized in a shared service, not duplicated across modules
* each approved unit belongs to one measurement family:

  * mass
  * volume
  * count

* each family has a canonical base:

  * mass -> `g`
  * volume -> `ml`
  * count -> `each`

* same-family conversion is supported in the first service slice
* cross-family conversion is not supported in the first service slice
* cross-family conversion will later require richer metadata such as density or recipe-level measurement definitions
* conversion service calls should return structured status, not just a number
* expected statuses currently include:

  * `direct_ratio`
  * `same_family_conversion`
  * `incompatible`
  * `unknown`
  * `missing`

* display rounding remains separate from conversion math
* the `according to taste` rule remains a render-layer behavior for tiny scaled values
* current extension:

  * recipes may use their own authoritative mass/volume fields as a bridge during live scaling
  * base foods may use their official mass/volume fields as a bridge in the shared conversion layer
  * base-food bridge conversion is defined for future reuse by modules such as Menu Builder or Inventory, even if current recipe rendering does not yet depend on it directly
  * hotel-pan units are modeled as approximate volume units with pan-size/depth UI controls for live scaling and Forecasting only

### 5D. Measurement Authority Model v0.1

Locked current direction:

* recipes keep batch `yield_quantity` / `yield_unit` plus measurement authority fields:

  * `mass_quantity`
  * `mass_unit`
  * `volume_quantity`
  * `volume_unit`

* recipe submitters should provide mass and volume yield data in the main recipe entry flow
* recipe submitters no longer provide serving fields in the main submit flow
* if recipe `yield_unit` is not `each`, the stored `yield_quantity` should be derived from the matching mass or volume basis rather than manually entered
* serving fields are reserved for dietitian-owned official portion data
* dietitian, admin, and super user roles may edit official serving data
* dietitian, admin, and super user roles may adjust recipe mass/volume data after submission
* base foods remain lightweight at submit time, but privileged edit flow may add official mass/volume basis data later
* privileged base-food edit flow may also add nutrition authority metadata such as nutrition group, calories per serving, and serving reference mass/volume
* base foods default `serving_count` to `1`
* recipes cannot go live until both mass and volume measurement fields are present
* future cross-family conversion work will build on these measurement authority fields

### 5E. Recipe Scaling Request Spec v0.1

Locked current direction:

* live recipe detail pages may accept a requested target quantity and target unit for scaling
* first scaling target is batch yield only
* target scaling uses same-family conversion into the recipe's stored batch yield unit
* recipes with `yield_unit = each` may still scale to mass or volume targets by anchoring the scale factor through the recipe's authoritative batch mass or batch volume
* unsupported target-unit relationships should return warnings rather than crashing the page
* scaled output should support both:

  * hierarchical direct-component view
  * flattened ordered sub-recipe view

* scaled flattened view should reuse the existing ordered sub-tree render contract
* display rounding remains render-layer behavior, including `according to taste` for values below `0.001`
* same-family scaling should be attempted first
* if same-family conversion fails and the target/request pair is mass<->volume, live recipe scaling may use the recipe's own authoritative mass and volume fields as a bridge
* richer scaled output may preserve the recipe's original ingredient units while also showing official mass or volume equivalents for ingredients and sub-recipes when authoritative bridge data exists
* live recipe detail pages may expose separate display toggles for:

  * display mode: `default`, `volume`, `mass`
  * unit system: `imperial`, `metric`

* `default` mode keeps the recipe's original component units in the main render
* `volume` and `mass` modes should convert display units through the shared conversion layer when possible
* display conversion should use a full logical cascade and choose the largest unit that renders at `>= 1`, stepping down to smaller units when needed
* count-based `each` components remain displayed as `each` across display modes
* broader cross-family conversion beyond recipe-level bridging remains deferred until density / richer conversion metadata is introduced

### 5F. Technical Detail Visibility

Locked current direction:

* item detail pages should default to a cleaner operational view
* technical/debug-oriented panels such as `Scaling Foundation` and `Audit` should be hidden by default
* privileged base-food nutrition authority metadata should also stay behind technical-details visibility
* reviewer, dietitian, admin, and super user roles may reveal those sections with a dedicated technical-details toggle
* workflow advanced view remains separate from technical-details visibility

### 6. Search Enhancements

Post-MVP:

* search behavior should stay centralized for reuse by future modules
* future module-specific filters can layer on top of the shared search core

### 7. Workflow / Auth Expansion

Current auth is mocked/parallel to MVP.
Future:

* real login/authentication
* richer super-user review flows
* reviewer return-for-revision tools
* `My Recipes` page
* public/shared live recipe collection views

## Guidance for Codex / Agent Work

When extending this project:

* preserve the unified `item` table model
* do not split base foods and recipes into separate master tables unless there is a strong reason and migration plan
* preserve the `recipe_component` dual-reference pattern
* keep base foods atomic in MVP behavior
* do not add workflow stages casually; status progression is locked for MVP
* keep frontend/editor state session-only until a deliberate draft-save design is approved
* keep instruction encoding/decoding logic isolated in the codec service layer
* treat current plain-text instruction storage as replaceable, not as hardcoded business logic
* avoid introducing frontend frameworks unless there is a strong need; current direction is intentionally lightweight
* respect current MVP boundaries and defer grouped methods, prettify logic, fuzzy search, and advanced scaling unless explicitly pulled into scope

## Perpetual Context Workflow

When a prompt mentions, proposes, plans, or defers a feature/function, update project documentation in the same turn so the idea is durable for future work.

Apply this even when the prompt frames the idea as later, deferred, "not now", or a brief aside. Capture the intent without implementing it unless the user explicitly asks for implementation.

Documentation placement:

* update `README.md` for user-facing current behavior, roadmap items, release notes, operational workflow notes, and visible feature status
* update `AGENT.md` for implementation guidance, constraints, testing rules, architecture expectations, deferred boundaries, and future agent context
* update both when the idea has both user-facing and agent-facing value

Documentation quality rules:

* keep additions brief and place them near the most relevant existing section
* distinguish implemented behavior from deferred or planned behavior
* preserve existing wording and roadmap intent unless the prompt explicitly changes direction
* do not let documentation updates expand the requested implementation scope

## Finish Workflow for Codex / Agent Work

Every completed prompt should end with a concise cumulative commit message suggestion.

Commit message workflow:

1. Track the user-visible work completed during the prompt and build on the previous suggestion when the prompt is a continuation of the same change set.
2. Use a fresh line-diff review when the prompt refines, rewrites, or refactors earlier work, because the final intent may differ from the incremental history.
3. For simple build-on prompts, do not perform a full line-by-line diff analysis unless needed; summarize from the known cumulative work plus a quick changed-file check.
4. For mixed or risky prompts, inspect the relevant diff hunks before writing the suggestion.
5. Provide the suggested message in the final response under `Suggested commit message`, using a short imperative subject and optional body bullets when helpful.

Preferred shape:

```text
Subject line in imperative mood

- Optional detail when more than one meaningful area changed
- Optional testing/verification note when it clarifies scope
```

## Pytest Workflow for Codex / Agent Work

Default test scope is module-local, not project-wide.

1. Start with focused tests for the changed submodule.
   - Run the directly affected domain test file or selected node ids.
   - Include the nearest one-level-up API or route coverage when behavior crosses the Flask boundary. In this repo that usually means selected `tests/test_routes.py::<test_name>` API/route tests, not the whole `test_routes.py` file unless the route layer itself is the working module.
2. Follow with a constrained module suite.
   - Treat the current working module as the feature area touched by the change, such as database/schema, item/workflow, recipe/scaling, menu/forecast, production record, search/query, or route/API.
   - Run only the test files that cover that feature area and its immediate public surface.
   - Do not run `.\.venv\Scripts\python.exe -m pytest -q` as the default confirmation step for ordinary Codex changes.
3. Reserve full-project pytest for explicit release/regression requests, broad shared-contract edits, dependency/tooling changes, or when the user asks for it.
4. After each pytest sequence, generated artifacts must be removed automatically. The pytest session hook in `tests/conftest.py` deletes `.test_tmp/run-*`, `.pytest_cache`, and project-local `__pycache__` directories after every run.

Current module-suite examples:

* database/schema: `tests/test_db_init.py tests/test_db_seed.py`
* item/workflow/notes: `tests/test_item_service.py tests/test_item_notes.py tests/test_policy_service.py tests/test_workflow.py` plus selected route tests for changed endpoints
* recipe authoring/scaling/detail: `tests/test_recipe_service.py tests/test_recipe_scaling_service.py tests/test_recipe_flattening_service.py tests/test_recipe_instruction_codec.py` plus selected recipe route tests
* menu builder: `tests/test_menu_service.py` plus selected menu route tests
* menu forecasting/production-facing forecast behavior: `tests/test_menu_forecast_service.py` plus selected forecast/production route tests
* search/query surfaces: `tests/test_queries.py` plus selected API search route tests
* route/API module work: selected node ids in `tests/test_routes.py`, broadening to the whole file only when route-wide behavior changed

Pytest module selectors:

* Tests are auto-tagged from `tests/conftest.py` with `module_*` and `relation_*` markers.
* Prefer readable selectors for suite runs: `.\.venv\Scripts\python.exe -m pytest -q --module-scope menu --relation-scope service`
* Run one-level-up API checks with: `.\.venv\Scripts\python.exe -m pytest -q --module-scope menu --relation-scope api`
* Multiple modules or relations are comma-separated, for example `--module-scope menu,forecast --relation-scope service,api`.
* Raw pytest marker expressions also work, for example `-m "module_recipe and relation_api"`.

Test data cleanup boundaries:

* Prefer real domain cleanup paths when they exist. Menu creation tests may delete the created menu because menu deletion is supported application behavior and cascades through menu slots.
* Do not add direct SQL deletion, voiding, or synthetic cleanup behavior for recipe/base-food item route tests unless the application gains an explicit item delete/archive workflow.
* Recipe and base-food tests should rely on isolated test databases and fixture teardown for cleanup. Directly deleting `item` rows can bypass workflow/event semantics, collide with component references, and create misleading coverage.
* SQLite `AUTOINCREMENT` gaps inside isolated test databases are acceptable and should not be optimized away. In the real app, item ids are durable identifiers, not sequence counters that need to stay gap-free.

## MVP Validation Checklist

1. run `.\.venv\Scripts\python.exe .\src\db.py`
2. run the constrained module-suite pytest command from the Pytest Workflow above
3. verify base food create, detail view, and reviewer/dietitian/admin workflow movement
4. verify recipe create, edit, return-to-submitter, resubmit, analyze, and live flow
5. verify notes, automatic workflow notifications, and notification clearing on item view
6. verify live item default view hides workflow notes/history, with advanced toggle for privileged roles
7. verify Menu Builder dated overview, slot assignment, bulk actions, and week/day print
8. verify Forecasting scaling, case mode, batch splits, production summary, and recipe scale links
9. verify Production Record current-day landing, formula entry, reason/notes, post/lock, review, CSV export, and print
10. verify Recipe print uses active scaling, flattened ingredients, display preferences, and sub-recipe grouping

## Schema Change Checklist

1. add a new numbered SQL migration in `database/migrations/`
2. put the schema/data change in that migration file
3. update `database/schema.sql` so the snapshot matches the latest DB shape
4. update app code, queries, services, templates, and tests as needed
5. run `.\.venv\Scripts\python.exe .\src\db.py`
6. run the database/schema module suite, then add only directly affected module/API tests
7. manually verify the affected workflow or UI behavior

## Current Next Logical Development Steps

1. begin Inventory Management foundation with item-linked inventory lines, current counts, count freshness, and item-linked pack/case definitions
2. define Forecasting / Production Record / Inventory API contracts for availability, expected demand, actual usage, and purchasing suggestions
3. add forecast error trend reporting by item over time using posted facts
4. refine posted facts only through versioned contract changes
5. defer analytics algorithms until usage, menu, inventory, purchasing, and cost record contracts are stable

