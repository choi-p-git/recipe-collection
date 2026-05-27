# Recipe Collection Agent Context

Status: MVP.

Primary route boundary: `/recipe-collection`.

## Current Scope

Recipe Collection owns culinary item identity and authoring workflows:

- `item` records for recipes and base foods.
- Recipe authoring with structured yield, measurement authority, ingredients, methods, and instruction text.
- Base-food submission with lightweight item name plus optional notes.
- Shared item detail page for recipes and base foods.
- Live collection browsing, item search, `My Recipes`, workflow notes/history, and preferences-driven display defaults.

Recipe Collection `item_id` remains the culinary ingredient identity reused by Menu Builder and Inventory. Inventory has its own catalog identity and bridges back to Recipe Collection items.

## Business Rules

- Item names are required and unique after normalization.
- Duplicate names use suffixes such as `Name (1)`, selecting highest existing suffix plus one.
- Item type is either `recipe` or `base_food`.
- Recipes require yield quantity/unit, primary cooking method, at least one ingredient, and at least one instruction step.
- Base foods do not require primary cooking method, recipe yield, or serving fields in MVP.
- Live item detail hides workflow notes/history by default; privileged roles may enable advanced workflow view.
- Base foods are shared system records, not personal-authored records.
- `My Recipes` is scoped to the active mock session user.

## Units And Measurement

- Standard authoring units are available in recipe/base-food create and edit flows.
- Advanced hotel-pan units are reserved for live recipe scaling, Forecasting, and future production-record workflows.
- Advanced hotel-pan units must not be accepted for recipe component units, recipe authoring yield units, recipe authoring measurement authority fields, or base-food authority fields.
- Recipe/base-food mass and volume authority fields support future scaling, conversion, nutrition, and inventory workflows.

## Recipe Scaling And Rendering

- Live recipe detail supports hierarchical and flattened ingredient views.
- Flattening is read-only and render-time.
- Scaling supports same-family conversions and bridge conversions through recipe/base-food mass/volume authority when available.
- Unsupported conversions should return structured warnings/status rather than silently producing bad quantities.
- Recipe print is a kitchen production sheet using active scale, flattened ingredients, display preferences, and sub-recipe grouping.

## Search

Search is DB-backed and shared for future module reuse. Current behavior supports exact match, prefix match, substring match, paged loading, collection browsing, and fuzzy fallback. Very short fuzzy fallbacks remain strict unless a picker explicitly relaxes after no result.

## Agent Implementation Guidance

- Keep Recipe Collection authoring simple and server-rendered.
- Keep instruction encoding/decoding isolated in `services/recipe_instruction_codec.py`.
- Treat plain-text instruction storage as replaceable business storage, not a permanent UI constraint.
- Keep workflow/status rules in service/policy layers.
- Do not introduce autosave or persistent drafts without a deliberate design.

## Testing Guidance

Use focused service tests plus route coverage when UI/API behavior changes:

```powershell
uv run pytest -q tests/test_recipe_service.py tests/test_recipe_scaling_service.py tests/test_recipe_flattening_service.py tests/test_recipe_instruction_codec.py --module-scope recipe --relation-scope service,unit
```

For item/workflow notes:

```powershell
uv run pytest -q tests/test_item_service.py tests/test_item_notes.py tests/test_policy_service.py tests/test_workflow.py --module-scope item,workflow --relation-scope service
```

## Roadmap

- Improve recipe/item detail presentation while preserving shared item route.
- Expand instruction model only after the current plain-text codec path remains stable.
- Add richer search enhancements only when needed by a concrete workflow.
- Keep customizable item type deferred.
