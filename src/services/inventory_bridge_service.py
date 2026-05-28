from db import get_connection, initialize_database
from config.item_categories import ITEM_CATEGORY_LABELS


MATCH_TYPES = {"manual", "legacy_item", "invoice_auto", "name_match", "vendor_code"}
MATCH_STATUSES = {"active", "review_needed", "rejected", "inactive"}
CATALOG_STATUSES = {"active", "review_needed", "inactive"}


class InvalidInventoryBridgeError(ValueError):
    """Raised when inventory catalog or item matching data is invalid."""


def _normalize_text(value, label: str, *, allow_blank: bool = False) -> str | None:
    normalized = " ".join(str(value or "").split())
    if not normalized:
        if allow_blank:
            return None
        raise InvalidInventoryBridgeError(f"{label} is required.")
    return normalized


def _normalize_optional_quantity(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        quantity = float(value)
    except (TypeError, ValueError):
        raise InvalidInventoryBridgeError("Quantity must be a valid number.")
    if quantity <= 0:
        raise InvalidInventoryBridgeError("Quantity must be greater than zero.")
    return round(quantity, 2)


def _normalize_confidence(value) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        raise InvalidInventoryBridgeError("Confidence score must be a valid number.")
    if confidence < 0 or confidence > 1:
        raise InvalidInventoryBridgeError("Confidence score must be between 0 and 1.")
    return confidence


def _format_quantity(value) -> str:
    rounded = round(float(value or 0), 2)
    if rounded == 0:
        return "0"
    return f"{rounded:g}"


def _catalog_payload(row) -> dict:
    return {
        "inventory_catalog_item_id": int(row[0]),
        "display_name": row[1],
        "vendor_name": row[2] or "",
        "vendor_item_code": row[3] or "",
        "purchase_uom": row[4] or "",
        "pack_quantity": row[5],
        "pack_quantity_display": _format_quantity(row[5]) if row[5] is not None else "",
        "pack_size_text": row[6] or "",
        "status": row[7],
        "created_at": row[8],
        "updated_at": row[9],
    }


def create_inventory_catalog_item(
    *,
    display_name: str,
    vendor_name: str | None = None,
    vendor_item_code: str | None = None,
    purchase_uom: str | None = None,
    pack_quantity=None,
    pack_size_text: str | None = None,
    status: str = "active",
) -> int:
    initialize_database()
    normalized_name = _normalize_text(display_name, "Display name")
    normalized_vendor_name = _normalize_text(vendor_name, "Vendor name", allow_blank=True)
    normalized_vendor_code = _normalize_text(vendor_item_code, "Vendor item code", allow_blank=True)
    normalized_purchase_uom = _normalize_text(purchase_uom, "Purchase UoM", allow_blank=True)
    normalized_pack_quantity = _normalize_optional_quantity(pack_quantity)
    normalized_pack_size = _normalize_text(pack_size_text, "Pack size", allow_blank=True)
    normalized_status = str(status or "").strip()
    if normalized_status not in CATALOG_STATUSES:
        raise InvalidInventoryBridgeError("Catalog status is invalid.")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO inventory_catalog_item (
                display_name,
                vendor_name,
                vendor_item_code,
                purchase_uom,
                pack_quantity,
                pack_size_text,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                normalized_name,
                normalized_vendor_name,
                normalized_vendor_code,
                normalized_purchase_uom,
                normalized_pack_quantity,
                normalized_pack_size,
                normalized_status,
            ),
        )
        catalog_item_id = int(cursor.lastrowid)
        conn.commit()
        return catalog_item_id


def create_inventory_item_match(
    *,
    recipe_collection_item_id,
    inventory_catalog_item_id,
    match_type: str = "manual",
    confidence_score=1,
    status: str = "active",
) -> int:
    initialize_database()
    try:
        recipe_item_id = int(recipe_collection_item_id)
        catalog_item_id = int(inventory_catalog_item_id)
    except (TypeError, ValueError):
        raise InvalidInventoryBridgeError("Select valid item records to match.")
    normalized_match_type = str(match_type or "").strip()
    normalized_status = str(status or "").strip()
    if normalized_match_type not in MATCH_TYPES:
        raise InvalidInventoryBridgeError("Match type is invalid.")
    if normalized_status not in MATCH_STATUSES:
        raise InvalidInventoryBridgeError("Match status is invalid.")
    normalized_confidence = _normalize_confidence(confidence_score)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT item_id FROM item WHERE item_id = ?",
            (recipe_item_id,),
        )
        if cursor.fetchone() is None:
            raise InvalidInventoryBridgeError("Recipe Collection item not found.")
        cursor.execute(
            "SELECT inventory_catalog_item_id FROM inventory_catalog_item WHERE inventory_catalog_item_id = ?",
            (catalog_item_id,),
        )
        if cursor.fetchone() is None:
            raise InvalidInventoryBridgeError("Inventory catalog item not found.")
        cursor.execute(
            """
            INSERT INTO inventory_item_match (
                recipe_collection_item_id,
                inventory_catalog_item_id,
                match_type,
                confidence_score,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                recipe_item_id,
                catalog_item_id,
                normalized_match_type,
                normalized_confidence,
                normalized_status,
            ),
        )
        match_id = int(cursor.lastrowid)
        conn.commit()
        return match_id


def ensure_legacy_inventory_match_for_item(
    *,
    recipe_collection_item_id,
    display_name: str,
    pack_quantity=None,
    pack_size_text: str | None = None,
    purchase_uom: str | None = None,
) -> int:
    initialize_database()
    try:
        recipe_item_id = int(recipe_collection_item_id)
    except (TypeError, ValueError):
        raise InvalidInventoryBridgeError("Recipe Collection item not found.")

    normalized_name = _normalize_text(display_name, "Display name")
    normalized_pack_quantity = _normalize_optional_quantity(pack_quantity)
    normalized_pack_size = _normalize_text(pack_size_text, "Pack size", allow_blank=True)
    normalized_purchase_uom = _normalize_text(purchase_uom, "Purchase UoM", allow_blank=True)

    with get_connection() as conn:
        cursor = conn.cursor()
        catalog_item_id = ensure_legacy_inventory_match_for_item_with_cursor(
            cursor=cursor,
            recipe_collection_item_id=recipe_item_id,
            display_name=normalized_name,
            pack_quantity=normalized_pack_quantity,
            pack_size_text=normalized_pack_size,
            purchase_uom=normalized_purchase_uom,
        )
        conn.commit()
        return catalog_item_id


def ensure_legacy_inventory_match_for_item_with_cursor(
    *,
    cursor,
    recipe_collection_item_id: int,
    display_name: str,
    pack_quantity=None,
    pack_size_text: str | None = None,
    purchase_uom: str | None = None,
) -> int:
    cursor.execute(
        """
        SELECT inventory_catalog_item_id
        FROM inventory_item_match
        WHERE recipe_collection_item_id = ?
          AND status = 'active'
        ORDER BY inventory_item_match_id DESC
        LIMIT 1
        """,
        (recipe_collection_item_id,),
    )
    row = cursor.fetchone()
    if row is not None:
        catalog_item_id = int(row[0])
        cursor.execute(
            """
            UPDATE inventory_catalog_item
            SET pack_quantity = COALESCE(?, pack_quantity),
                pack_size_text = COALESCE(?, pack_size_text),
                purchase_uom = COALESCE(?, purchase_uom),
                updated_at = datetime('now')
            WHERE inventory_catalog_item_id = ?
            """,
            (pack_quantity, pack_size_text, purchase_uom, catalog_item_id),
        )
        return catalog_item_id

    cursor.execute(
        """
        INSERT INTO inventory_catalog_item (
            display_name,
            purchase_uom,
            pack_quantity,
            pack_size_text,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, 'active', datetime('now'), datetime('now'))
        """,
        (display_name, purchase_uom, pack_quantity, pack_size_text),
    )
    catalog_item_id = int(cursor.lastrowid)
    cursor.execute(
        """
        INSERT INTO inventory_item_match (
            recipe_collection_item_id,
            inventory_catalog_item_id,
            match_type,
            confidence_score,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, 'legacy_item', 1, 'active', datetime('now'), datetime('now'))
        """,
        (recipe_collection_item_id, catalog_item_id),
    )
    return catalog_item_id


def resolve_inventory_for_recipe_item(recipe_collection_item_id) -> dict:
    initialize_database()
    try:
        recipe_item_id = int(recipe_collection_item_id)
    except (TypeError, ValueError):
        raise InvalidInventoryBridgeError("Recipe Collection item not found.")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                ici.inventory_catalog_item_id,
                ici.display_name,
                ici.vendor_name,
                ici.vendor_item_code,
                ici.purchase_uom,
                ici.pack_quantity,
                ici.pack_size_text,
                ici.status,
                ici.created_at,
                ici.updated_at,
                iim.inventory_item_match_id,
                iim.match_type,
                iim.confidence_score,
                iim.status
            FROM inventory_item_match iim
            JOIN inventory_catalog_item ici
              ON ici.inventory_catalog_item_id = iim.inventory_catalog_item_id
            WHERE iim.recipe_collection_item_id = ?
              AND iim.status = 'active'
            ORDER BY iim.inventory_item_match_id DESC
            LIMIT 1
            """,
            (recipe_item_id,),
        )
        row = cursor.fetchone()

    if row is None:
        return {
            "recipe_collection_item_id": recipe_item_id,
            "inventory_catalog_item_id": None,
            "match_status": "unmatched",
            "match_type": "",
            "confidence_score": 0,
            "catalog_item": None,
        }

    return {
        "recipe_collection_item_id": recipe_item_id,
        "inventory_catalog_item_id": int(row[0]),
        "match_status": row[13],
        "match_type": row[11],
        "confidence_score": float(row[12]),
        "inventory_item_match_id": int(row[10]),
        "catalog_item": _catalog_payload(row[:10]),
    }


def get_inventory_availability_for_items(recipe_collection_item_ids: list[int]) -> list[dict]:
    initialize_database()
    normalized_ids = []
    for item_id in recipe_collection_item_ids:
        try:
            normalized_ids.append(int(item_id))
        except (TypeError, ValueError):
            continue
    if not normalized_ids:
        return []

    placeholders = ", ".join("?" for _ in normalized_ids)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT
                i.item_id,
                i.item_name,
                ici.inventory_catalog_item_id,
                ici.display_name,
                iim.match_type,
                iim.confidence_score,
                COALESCE(iim.status, 'unmatched') AS match_status,
                ili.unit,
                SUM(CASE WHEN il.status = 'active' THEN COALESCE(ili.quantity, 0) ELSE 0 END) AS on_hand_quantity,
                COUNT(DISTINCT CASE WHEN il.status = 'active' THEN ili.inventory_location_id END) AS location_count,
                MAX(CASE WHEN il.status = 'active' THEN ili.updated_at END) AS last_counted_at,
                ici.purchase_uom,
                ici.pack_quantity,
                ici.pack_size_text
            FROM item i
            LEFT JOIN inventory_item_match iim
              ON iim.recipe_collection_item_id = i.item_id
             AND iim.status = 'active'
            LEFT JOIN inventory_catalog_item ici
              ON ici.inventory_catalog_item_id = iim.inventory_catalog_item_id
            LEFT JOIN inventory_location_item ili
              ON ili.item_id = i.item_id
            LEFT JOIN inventory_location il
              ON il.inventory_location_id = ili.inventory_location_id
            WHERE i.item_id IN ({placeholders})
            GROUP BY i.item_id, ili.unit
            ORDER BY i.item_name ASC, ili.unit ASC
            """,
            normalized_ids,
        )
        rows = cursor.fetchall()

    return [
        {
            "recipe_collection_item_id": int(row[0]),
            "recipe_collection_item_name": row[1],
            "inventory_catalog_item_id": int(row[2]) if row[2] is not None else None,
            "inventory_catalog_display_name": row[3] or "",
            "match_type": row[4] or "",
            "confidence_score": float(row[5] or 0),
            "match_status": row[6],
            "on_hand_unit": row[7] or "",
            "on_hand_quantity": float(row[8] or 0),
            "on_hand_quantity_display": _format_quantity(row[8]),
            "location_count": int(row[9] or 0),
            "last_counted_at": row[10] or "",
            "purchase_uom": row[11] or "",
            "pack_quantity": row[12],
            "pack_quantity_display": _format_quantity(row[12]) if row[12] is not None else "",
            "pack_size_text": row[13] or "",
        }
        for row in rows
    ]


def _catalog_review_classification(row: dict) -> dict:
    if not row["inventory_item_match_id"]:
        return {
            "review_status": "unmatched",
            "review_status_label": "Unmatched",
            "review_reason": "No inventory catalog match exists yet.",
            "needs_review": True,
        }
    if row["match_status"] == "review_needed" or row["catalog_status"] == "review_needed":
        return {
            "review_status": "review_needed",
            "review_status_label": "Needs Review",
            "review_reason": "Match or catalog item is marked for review.",
            "needs_review": True,
        }
    if row["match_type"] in {"invoice_auto", "name_match", "vendor_code"}:
        return {
            "review_status": "auto_match",
            "review_status_label": "Auto Match",
            "review_reason": "Auto/vendor-derived match should be reviewed before relying on invoices.",
            "needs_review": True,
        }
    if row["match_type"] == "legacy_item":
        return {
            "review_status": "legacy_match",
            "review_status_label": "Legacy Match",
            "review_reason": "Created from existing inventory count entry; review before invoice automation.",
            "needs_review": True,
        }
    return {
        "review_status": "manual_match",
        "review_status_label": "Manual Match",
        "review_reason": "Manual match is active.",
        "needs_review": False,
    }


def get_inventory_catalog_review_page(*, scope: str = "relevant", actor_user_id: str | None = None) -> dict:
    initialize_database()
    normalized_scope = str(scope or "relevant").strip()
    if normalized_scope not in {"relevant", "all"}:
        normalized_scope = "relevant"
    query_params = []
    scope_filter = ""
    if normalized_scope == "relevant":
        from services.inventory_usage_service import get_inventory_reorder_plan

        planning_item_ids = sorted(
            {
                int(row["item_id"])
                for row in get_inventory_reorder_plan(
                    actor_user_id=actor_user_id,
                    operation_day_limit=3,
                )["rows"]
            }
        )
        planning_placeholders = ", ".join("?" for _ in planning_item_ids) or "NULL"
        query_params.extend(planning_item_ids)
        scope_filter = """
              AND (
                i.item_id IN ({planning_placeholders})
                OR lm.match_status = 'review_needed'
                OR ici.status = 'review_needed'
                OR lm.match_type IN ('invoice_auto', 'name_match', 'vendor_code')
              )
        """.format(planning_placeholders=planning_placeholders)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            WITH latest_match AS (
                SELECT
                    iim.inventory_item_match_id,
                    iim.recipe_collection_item_id,
                    iim.inventory_catalog_item_id,
                    iim.match_type,
                    iim.confidence_score,
                    iim.status AS match_status,
                    iim.updated_at AS match_updated_at
                FROM inventory_item_match iim
                WHERE iim.status IN ('active', 'review_needed')
                  AND iim.inventory_item_match_id = (
                    SELECT iim2.inventory_item_match_id
                    FROM inventory_item_match iim2
                    WHERE iim2.recipe_collection_item_id = iim.recipe_collection_item_id
                      AND iim2.status IN ('active', 'review_needed')
                    ORDER BY
                        CASE WHEN iim2.status = 'review_needed' THEN 0 ELSE 1 END,
                        iim2.inventory_item_match_id DESC
                    LIMIT 1
                  )
            )
            SELECT
                i.item_id,
                i.item_name,
                i.item_category,
                i.status,
                lm.inventory_item_match_id,
                lm.inventory_catalog_item_id,
                lm.match_type,
                lm.confidence_score,
                lm.match_status,
                lm.match_updated_at,
                ici.display_name,
                ici.vendor_name,
                ici.vendor_item_code,
                ici.purchase_uom,
                ici.pack_quantity,
                ici.pack_size_text,
                ici.status AS catalog_status
            FROM item i
            LEFT JOIN latest_match lm
              ON lm.recipe_collection_item_id = i.item_id
            LEFT JOIN inventory_catalog_item ici
              ON ici.inventory_catalog_item_id = lm.inventory_catalog_item_id
            WHERE i.status = 'live'
              AND i.item_type = 'base_food'
              {scope_filter}
            ORDER BY
                CASE
                    WHEN lm.inventory_item_match_id IS NULL THEN 0
                    WHEN lm.match_status = 'review_needed' OR ici.status = 'review_needed' THEN 1
                    WHEN lm.match_type IN ('invoice_auto', 'name_match', 'vendor_code') THEN 2
                    WHEN lm.match_type = 'legacy_item' THEN 3
                    ELSE 4
                END,
                i.item_name ASC
            """,
            query_params,
        )
        rows = cursor.fetchall()

    review_rows = []
    for row in rows:
        payload = {
            "item_id": int(row[0]),
            "item_name": row[1],
            "item_category": row[2],
            "item_category_label": ITEM_CATEGORY_LABELS.get(row[2], str(row[2] or "").title()),
            "item_status": row[3],
            "inventory_item_match_id": int(row[4]) if row[4] is not None else None,
            "inventory_catalog_item_id": int(row[5]) if row[5] is not None else None,
            "match_type": row[6] or "",
            "match_type_label": str(row[6] or "unmatched").replace("_", " ").title(),
            "confidence_score": float(row[7] or 0),
            "confidence_percent_display": f"{round(float(row[7] or 0) * 100):g}%",
            "match_status": row[8] or "unmatched",
            "match_updated_at": row[9] or "",
            "catalog_display_name": row[10] or "",
            "vendor_name": row[11] or "",
            "vendor_item_code": row[12] or "",
            "purchase_uom": row[13] or "",
            "pack_quantity": row[14],
            "pack_quantity_display": _format_quantity(row[14]) if row[14] is not None else "",
            "pack_size_text": row[15] or "",
            "catalog_status": row[16] or "",
        }
        review_rows.append({**payload, **_catalog_review_classification(payload)})

    totals = {
        "row_count": len(review_rows),
        "needs_review_count": len([row for row in review_rows if row["needs_review"]]),
        "unmatched_count": len([row for row in review_rows if row["review_status"] == "unmatched"]),
        "legacy_match_count": len([row for row in review_rows if row["review_status"] == "legacy_match"]),
        "auto_match_count": len([row for row in review_rows if row["review_status"] == "auto_match"]),
        "manual_match_count": len([row for row in review_rows if row["review_status"] == "manual_match"]),
    }
    return {
        "rows": review_rows,
        "totals": totals,
        "scope": normalized_scope,
        "scope_label": "Relevant Inventory Items" if normalized_scope == "relevant" else "All Live Base Foods",
        "contract_version": "inventory.catalog_review.v1",
    }
