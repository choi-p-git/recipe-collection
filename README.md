Recipe Collection System
Project Summary

The Recipe Collection System is a modular, database-driven application for managing recipes and base food submissions in a structured environment. It is designed as an MVP foundation for future menu planning, production, scaling, and nutrition-analysis workflows.

Current MVP behavior

- Recipes are structured records with yield, optional serving data, ingredients, methods, and a primary cooking method.
- Base foods are lightweight approval submissions with only an item name and optional notes.
- A shared item detail page supports both recipes and base foods.
- Mock auth/login is session-backed for MVP development and role testing.
- Reviewer, dietitian, and admin workflow portals support status movement across the MVP lifecycle.
- Workflow history, note threads, and notifications are active across the review lifecycle.

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

2. Mock auth shell
Session-backed mock login page
Existing account switcher
Direct mock user creation with role selection
Debug override panel for account, role, and display name testing

3. Base food workflow
Minimal base food submission form
Whitespace normalization and case-insensitive duplicate protection
Duplicate-name suggestion flow
Successful submit redirects to shared item detail page

4. Recipe workflow
Single-page multi-section recipe editor
Client-side validation with section warnings
Database-backed ingredient search
Recipe submit flow inserts item row and component rows
Recipe authorship follows the active mock session user
Instruction codec stores ordered method steps as numbered text

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

Database migration/versioning note

- Add future schema changes as a new numbered SQL file in `database/migrations/`
- Keep migration filenames ordered, for example `0002_add_workflow_event.sql`
- `src/db.py` applies pending migrations and records them in the `schema_migration` table
- `database/schema.sql` remains the latest full snapshot for rebuild/reference use
- Existing local databases without migration history are stamped forward the first time the migration runner sees them

MVP validation checklist

1. Run `.\.venv\Scripts\python.exe .\src\db.py`
2. Run `.\.venv\Scripts\python.exe -m pytest -q`
3. Verify base food create, detail view, and reviewer/dietitian/admin workflow movement
4. Verify recipe create, edit, return-to-submitter, resubmit, analyze, and live flow
5. Verify notes, automatic workflow notifications, and notification clearing on item view
6. Verify live item default view hides workflow notes/history, with advanced toggle for privileged roles

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
