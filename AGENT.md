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

  * 20 base foods
  * 5 simple recipes using only base foods
  * 3 complex recipes using both base foods and recipes

* seed loading is idempotent and only runs when the `item` table is empty
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

* `/items/<item_id>`
* legacy `/recipes/<recipe_id>` redirects to the shared item route

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

### 2. Menu Builder Integration

* live recipes available for selection in Menu Builder
* later use recipe/base food items in broader planning workflows

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

* drag-and-drop is deferred to a later release
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
* first Menu Builder release should defer:

  * drag-and-drop
  * rules engine / conditional checks
  * slot-level scaling overrides
  * nutrition balancing
  * inventory rollups

* rules checks and conditional checks should be implemented only after base Menu Builder object behavior is stable

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

## MVP Validation Checklist

1. run `.\.venv\Scripts\python.exe .\src\db.py`
2. run `.\.venv\Scripts\python.exe -m pytest -q`
3. verify base food create, detail view, and reviewer/dietitian/admin workflow movement
4. verify recipe create, edit, return-to-submitter, resubmit, analyze, and live flow
5. verify notes, automatic workflow notifications, and notification clearing on item view
6. verify live item default view hides workflow notes/history, with advanced toggle for privileged roles

## Schema Change Checklist

1. add a new numbered SQL migration in `database/migrations/`
2. put the schema/data change in that migration file
3. update `database/schema.sql` so the snapshot matches the latest DB shape
4. update app code, queries, services, templates, and tests as needed
5. run `.\.venv\Scripts\python.exe .\src\db.py`
6. run `.\.venv\Scripts\python.exe -m pytest -q`
7. manually verify the affected workflow or UI behavior

## Current Next Logical Development Steps

1. draft first Menu Builder schema and route/service path from `Menu Builder Spec v0.1`
2. implement Menu Builder create flow
3. implement Menu overview shell and slot assignment flow
