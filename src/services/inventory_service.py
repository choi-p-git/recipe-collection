import sqlite3

from config.item_categories import ITEM_CATEGORY_LABELS
from config.units import STANDARD_UNITS
from db import get_connection, initialize_database
from services.inventory_bridge_service import ensure_legacy_inventory_match_for_item_with_cursor
from services.unit_conversion_service import normalize_unit_symbol
from services.unit_label_service import format_unit_label


INVENTORY_UNIT_SET = set(STANDARD_UNITS)
INVENTORY_UOM_OPTIONS = ("Case", "Each", "Kg", "Lb")
INVENTORY_COUNT_TYPES = {
    "counted_by_each_only": "counted by each only",
    "counted_by_case_only": "counted by case only",
    "counted_by_each_and_case": "counted by each and case",
}


class InvalidInventoryError(ValueError):
    """Raised when inventory data is invalid."""


def _normalize_name(value, label: str) -> str:
    normalized = " ".join(str(value or "").split())
    if not normalized:
        raise InvalidInventoryError(f"{label} is required.")
    return normalized


def _normalize_quantity(value, *, allow_blank: bool = False) -> float | None:
    if allow_blank and value in (None, ""):
        return None
    try:
        quantity = float(value)
    except (TypeError, ValueError):
        raise InvalidInventoryError("Quantity must be a valid number.")
    if quantity < 0:
        raise InvalidInventoryError("Quantity cannot be negative.")
    return quantity


def _normalize_inventory_unit(value, *, allow_blank: bool = False) -> str | None:
    normalized = normalize_unit_symbol(value)
    if allow_blank and not normalized:
        return None
    if normalized not in INVENTORY_UNIT_SET:
        raise InvalidInventoryError("Select a standard inventory unit.")
    return normalized


def _format_quantity(value) -> str:
    rounded = round(float(value or 0), 2)
    if rounded == 0:
        return "0"
    return f"{rounded:g}"


def _format_current_on_hand_display(row: dict) -> dict:
    quantity = float(row["quantity"] or 0)
    unit = row["unit"]
    if row.get("unit_of_measurement") == "Case" and row.get("case_quantity") is not None:
        case_quantity = float(row.get("case_quantity") or 0)
        each_quantity = float(row.get("each_quantity") or 0)
        has_case_entry = float(row.get("count_case_quantity") or 0) > 0
        if has_case_entry and case_quantity >= 0.25:
            return {
                "display_quantity": case_quantity,
                "display_quantity_display": _format_quantity(case_quantity),
                "display_unit": "case",
                "display_unit_label": "case",
            }
        return {
            "display_quantity": each_quantity,
            "display_quantity_display": _format_quantity(each_quantity),
            "display_unit": "each",
            "display_unit_label": format_unit_label("each"),
        }
    return {
        "display_quantity": quantity,
        "display_quantity_display": _format_quantity(quantity),
        "display_unit": unit,
        "display_unit_label": format_unit_label(unit),
    }


def _format_location_line_display(row: dict) -> dict:
    quantity = float(row["quantity"] or 0)
    unit = row["unit"]
    if row.get("unit_of_measurement") == "Case":
        count_type = row.get("count_type")
        count_case_quantity = float(row.get("count_case_quantity") or 0)
        pack_quantity = row.get("pack_quantity")
        has_case_display = count_type in {"counted_by_case_only", "counted_by_each_and_case"}
        if has_case_display and count_case_quantity > 0 and quantity >= 0.25:
            return {
                "display_quantity": quantity,
                "display_quantity_display": _format_quantity(quantity),
                "display_unit": "case",
                "display_unit_label": "case",
            }
        if has_case_display and pack_quantity:
            each_quantity = (count_case_quantity * float(pack_quantity)) + float(row.get("count_each_quantity") or 0)
            return {
                "display_quantity": each_quantity,
                "display_quantity_display": _format_quantity(each_quantity),
                "display_unit": "each",
                "display_unit_label": format_unit_label("each"),
            }
    return {
        "display_quantity": quantity,
        "display_quantity_display": _format_quantity(quantity),
        "display_unit": unit,
        "display_unit_label": format_unit_label(unit),
    }


def _normalize_optional_pack_quantity(value) -> float | None:
    quantity = _normalize_quantity(value, allow_blank=True)
    if quantity is None:
        return None
    return round(quantity, 2)


def _normalize_pack_size_text(value) -> str | None:
    normalized = " ".join(str(value or "").split())
    return normalized or None


def _normalize_uom(value) -> str:
    normalized = " ".join(str(value or "").split())
    if normalized not in INVENTORY_UOM_OPTIONS:
        raise InvalidInventoryError("Select a valid unit of measurement.")
    return normalized


def _normalize_count_type(value) -> str:
    normalized = str(value or "").strip()
    if normalized not in INVENTORY_COUNT_TYPES:
        raise InvalidInventoryError("Select a valid count type.")
    return normalized


def _storage_unit_for_uom(unit_of_measurement: str) -> str:
    if unit_of_measurement == "Kg":
        return "kg"
    if unit_of_measurement == "Lb":
        return "lb"
    return "each"


def _calculate_normalized_quantity(
    *,
    count_each_quantity: float,
    count_case_quantity: float,
    pack_quantity: float | None,
    unit_of_measurement: str,
    count_type: str,
) -> float:
    if unit_of_measurement in {"Kg", "Lb"}:
        return round(count_each_quantity, 2)
    if count_type == "counted_by_case_only":
        return round(count_case_quantity, 2)
    if count_type == "counted_by_each_and_case":
        each_fraction = count_each_quantity / pack_quantity if pack_quantity else 0
        return round(count_case_quantity + each_fraction, 2)
    return round(count_each_quantity, 2)


def _build_pack_summary(row: dict) -> str:
    pack_quantity = row.get("pack_quantity_display")
    pack_size_text = row.get("pack_size_text")
    unit_of_measurement = row.get("unit_of_measurement")
    if pack_quantity and pack_size_text and unit_of_measurement == "Case":
        return f"{pack_quantity} packs x {pack_size_text}"
    if pack_quantity and pack_size_text:
        return f"{pack_quantity} x {pack_size_text} per {unit_of_measurement}"
    if pack_size_text:
        return pack_size_text
    return "--"


def build_inventory_item_interpretation(
    *,
    item_name: str,
    pack_quantity,
    pack_size_text,
    unit_of_measurement,
    count_type,
) -> str:
    normalized_uom = _normalize_uom(unit_of_measurement)
    normalized_count_type = _normalize_count_type(count_type)
    normalized_pack_quantity = _normalize_optional_pack_quantity(pack_quantity)
    normalized_pack_size = _normalize_pack_size_text(pack_size_text)
    count_label = INVENTORY_COUNT_TYPES[normalized_count_type]
    if normalized_pack_quantity and normalized_pack_size and normalized_uom == "Case":
        verb = "is" if normalized_pack_quantity == 1 else "are"
        pack_label = "pack" if normalized_pack_quantity == 1 else "packs"
        return (
            f"Per case, there {verb} {_format_quantity(normalized_pack_quantity)} {pack_label} of "
            f"{normalized_pack_size} {item_name}. It is to be {count_label}."
        )
    if normalized_pack_quantity and normalized_pack_size:
        verb = "is" if normalized_pack_quantity == 1 else "are"
        pack_label = "pack" if normalized_pack_quantity == 1 else "packs"
        return (
            f"Per {normalized_uom.lower()}, there {verb} {_format_quantity(normalized_pack_quantity)} {pack_label} of "
            f"{normalized_pack_size} {item_name}. It is to be {count_label}."
        )
    return f"{item_name} is measured as {normalized_uom}. It is to be {count_label}."


def _line_payload(row) -> dict:
    payload = {
        "inventory_location_item_id": int(row[0]),
        "inventory_location_id": int(row[1]),
        "item_id": int(row[2]),
        "item_name": row[3],
        "item_type": row[4],
        "quantity": float(row[5]),
        "quantity_display": _format_quantity(row[5]),
        "unit": row[6],
        "unit_label": format_unit_label(row[6]),
        "count_each_quantity": float(row[7] or 0),
        "count_each_quantity_display": _format_quantity(row[7]),
        "count_case_quantity": float(row[8] or 0),
        "count_case_quantity_display": _format_quantity(row[8]),
        "pack_quantity": row[9],
        "pack_quantity_display": _format_quantity(row[9]) if row[9] is not None else "",
        "pack_size_text": row[10] or "",
        "unit_of_measurement": row[11],
        "count_type": row[12],
        "count_type_label": INVENTORY_COUNT_TYPES.get(row[12], row[12]),
        "display_sequence": int(row[13] or 0),
        "updated_at": row[14],
        "last_price_display": "TBI",
        "extension_price_display": "TBI",
    }
    payload["pack_summary"] = _build_pack_summary(payload)
    payload.update(_format_location_line_display(payload))
    payload["interpretation"] = build_inventory_item_interpretation(
        item_name=payload["item_name"],
        pack_quantity=payload["pack_quantity"],
        pack_size_text=payload["pack_size_text"],
        unit_of_measurement=payload["unit_of_measurement"],
        count_type=payload["count_type"],
    )
    return payload


def _break_payload(row) -> dict:
    return {
        "row_type": "break",
        "inventory_location_break_id": int(row[0]),
        "inventory_location_id": int(row[1]),
        "break_label": row[2],
        "display_sequence": int(row[3] or 0),
        "updated_at": row[4],
    }


def _next_display_sequence(cursor, inventory_location_id: int) -> int:
    cursor.execute(
        """
        SELECT MAX(display_sequence)
        FROM (
            SELECT display_sequence
            FROM inventory_location_item
            WHERE inventory_location_id = ?
            UNION ALL
            SELECT display_sequence
            FROM inventory_location_break
            WHERE inventory_location_id = ?
        )
        """,
        (inventory_location_id, inventory_location_id),
    )
    row = cursor.fetchone()
    return int(row[0] or 0) + 10


def _ensure_parent_location(cursor, parent_inventory_location_id) -> int | None:
    if parent_inventory_location_id in (None, ""):
        return None
    try:
        parent_id = int(parent_inventory_location_id)
    except (TypeError, ValueError):
        raise InvalidInventoryError("Parent location is invalid.")
    cursor.execute(
        """
        SELECT inventory_location_id, parent_inventory_location_id, status
        FROM inventory_location
        WHERE inventory_location_id = ?
        """,
        (parent_id,),
    )
    parent_row = cursor.fetchone()
    if parent_row is None:
        raise InvalidInventoryError("Parent location not found.")
    if parent_row[1] is not None:
        raise InvalidInventoryError("Sub-storage locations cannot have child locations yet.")
    if parent_row[2] != "active":
        raise InvalidInventoryError("Parent location is inactive.")
    return parent_id


def create_inventory_location(
    *,
    location_name: str,
    actor_user_id: str,
    actor_display_name: str,
    parent_inventory_location_id=None,
) -> int:
    initialize_database()
    normalized_name = _normalize_name(location_name, "Location name")

    with get_connection() as conn:
        cursor = conn.cursor()
        parent_id = _ensure_parent_location(cursor, parent_inventory_location_id)
        try:
            cursor.execute(
                """
                INSERT INTO inventory_location (
                    parent_inventory_location_id,
                    location_name,
                    status,
                    created_by_user_id,
                    created_by_display_name,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, 'active', ?, ?, datetime('now'), datetime('now'))
                """,
                (parent_id, normalized_name, actor_user_id, actor_display_name),
            )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc).upper():
                raise InvalidInventoryError("Inventory location already exists for this level.")
            raise
        location_id = int(cursor.lastrowid)
        conn.commit()
        return location_id


def rename_inventory_location(*, inventory_location_id, location_name: str) -> None:
    initialize_database()
    try:
        location_id = int(inventory_location_id)
    except (TypeError, ValueError):
        raise InvalidInventoryError("Inventory location not found.")
    normalized_name = _normalize_name(location_name, "Location name")

    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE inventory_location
                SET location_name = ?,
                    updated_at = datetime('now')
                WHERE inventory_location_id = ?
                """,
                (normalized_name, location_id),
            )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc).upper():
                raise InvalidInventoryError("Inventory location already exists for this level.")
            raise
        if cursor.rowcount == 0:
            raise InvalidInventoryError("Inventory location not found.")
        conn.commit()


def delete_inventory_location(*, inventory_location_id) -> None:
    initialize_database()
    try:
        location_id = int(inventory_location_id)
    except (TypeError, ValueError):
        raise InvalidInventoryError("Inventory location not found.")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT inventory_location_id FROM inventory_location WHERE inventory_location_id = ?",
            (location_id,),
        )
        if cursor.fetchone() is None:
            raise InvalidInventoryError("Inventory location not found.")
        cursor.execute(
            """
            SELECT inventory_location_id
            FROM inventory_location
            WHERE parent_inventory_location_id = ?
            """,
            (location_id,),
        )
        child_ids = [int(row[0]) for row in cursor.fetchall()]
        target_ids = [location_id, *child_ids]
        placeholders = ", ".join("?" for _ in target_ids)
        cursor.execute(
            f"DELETE FROM inventory_location_item WHERE inventory_location_id IN ({placeholders})",
            target_ids,
        )
        cursor.execute(
            f"DELETE FROM inventory_location WHERE inventory_location_id IN ({placeholders})",
            target_ids,
        )
        conn.commit()


def list_inventory_locations(*, include_inactive: bool = False) -> list[dict]:
    initialize_database()
    status_filter = "" if include_inactive else "WHERE status = 'active'"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT
                inventory_location_id,
                parent_inventory_location_id,
                location_name,
                status,
                created_at,
                updated_at
            FROM inventory_location
            {status_filter}
            ORDER BY parent_inventory_location_id IS NOT NULL ASC,
                     location_name ASC,
                     inventory_location_id ASC
            """
        )
        return [
            {
                "inventory_location_id": int(row[0]),
                "parent_inventory_location_id": int(row[1]) if row[1] is not None else None,
                "location_name": row[2],
                "status": row[3],
                "created_at": row[4],
                "updated_at": row[5],
            }
            for row in cursor.fetchall()
        ]


def get_inventory_location_tree() -> list[dict]:
    locations = list_inventory_locations(include_inactive=False)
    children_by_parent: dict[int, list[dict]] = {}
    roots = []
    for location in locations:
        location = {**location, "children": []}
        if location["parent_inventory_location_id"] is None:
            roots.append(location)
        else:
            children_by_parent.setdefault(location["parent_inventory_location_id"], []).append(location)
    for root in roots:
        root["children"] = children_by_parent.get(root["inventory_location_id"], [])
    return roots


def get_inventory_location_detail(inventory_location_id) -> dict | None:
    initialize_database()
    try:
        location_id = int(inventory_location_id)
    except (TypeError, ValueError):
        return None
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                inventory_location_id,
                parent_inventory_location_id,
                location_name,
                status,
                created_at,
                updated_at
            FROM inventory_location
            WHERE inventory_location_id = ?
            """,
            (location_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        location = {
            "inventory_location_id": int(row[0]),
            "parent_inventory_location_id": int(row[1]) if row[1] is not None else None,
            "location_name": row[2],
            "status": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }
        cursor.execute(
            """
            SELECT inventory_location_id, location_name, status, created_at, updated_at
            FROM inventory_location
            WHERE parent_inventory_location_id = ?
            ORDER BY location_name ASC, inventory_location_id ASC
            """,
            (location_id,),
        )
        location["children"] = [
            {
                "inventory_location_id": int(child_row[0]),
                "location_name": child_row[1],
                "status": child_row[2],
                "created_at": child_row[3],
                "updated_at": child_row[4],
            }
            for child_row in cursor.fetchall()
        ]
    location["item_rows"] = list_inventory_location_items(location_id)
    location["count_rows"] = list_inventory_location_count_rows(location_id)
    return location


def list_inventory_location_items(inventory_location_id) -> list[dict]:
    initialize_database()
    try:
        location_id = int(inventory_location_id)
    except (TypeError, ValueError):
        return []
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                ili.inventory_location_item_id,
                ili.inventory_location_id,
                ili.item_id,
                i.item_name,
                i.item_type,
                ili.quantity,
                ili.unit,
                ili.count_each_quantity,
                ili.count_case_quantity,
                ili.pack_quantity,
                ili.pack_size_text,
                ili.unit_of_measurement,
                ili.count_type,
                ili.display_sequence,
                ili.updated_at
            FROM inventory_location_item ili
            JOIN item i
              ON i.item_id = ili.item_id
            WHERE ili.inventory_location_id = ?
            ORDER BY ili.display_sequence ASC, i.item_name ASC, ili.inventory_location_item_id ASC
            """,
            (location_id,),
        )
        return [_line_payload(row) for row in cursor.fetchall()]


def list_inventory_location_breaks(inventory_location_id) -> list[dict]:
    initialize_database()
    try:
        location_id = int(inventory_location_id)
    except (TypeError, ValueError):
        return []
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                inventory_location_break_id,
                inventory_location_id,
                break_label,
                display_sequence,
                updated_at
            FROM inventory_location_break
            WHERE inventory_location_id = ?
            ORDER BY display_sequence ASC, inventory_location_break_id ASC
            """,
            (location_id,),
        )
        return [_break_payload(row) for row in cursor.fetchall()]


def list_inventory_location_count_rows(inventory_location_id) -> list[dict]:
    item_rows = [{**row, "row_type": "item"} for row in list_inventory_location_items(inventory_location_id)]
    break_rows = list_inventory_location_breaks(inventory_location_id)
    return sorted(
        [*item_rows, *break_rows],
        key=lambda row: (
            row["display_sequence"],
            0 if row["row_type"] == "break" else 1,
            row.get("inventory_location_break_id") or row.get("inventory_location_item_id") or 0,
        ),
    )


def save_inventory_location_item(
    *,
    inventory_location_id,
    item_id,
    quantity=None,
    unit=None,
    count_each_quantity=None,
    count_case_quantity=None,
    pack_quantity=None,
    pack_size_text=None,
    unit_of_measurement="Case",
    count_type="counted_by_each_only",
    pack_size_quantity=None,
    pack_size_unit=None,
) -> dict:
    initialize_database()
    try:
        location_id = int(inventory_location_id)
        normalized_item_id = int(item_id)
    except (TypeError, ValueError):
        raise InvalidInventoryError("Select a valid inventory item.")
    normalized_each_quantity = _normalize_quantity(
        count_each_quantity if count_each_quantity is not None else quantity or 0,
        allow_blank=True,
    ) or 0
    normalized_case_quantity = _normalize_quantity(count_case_quantity, allow_blank=True) or 0
    normalized_pack_quantity = _normalize_optional_pack_quantity(
        pack_quantity if pack_quantity not in (None, "") else pack_size_quantity
    )
    normalized_pack_size_text = _normalize_pack_size_text(pack_size_text)
    if not normalized_pack_size_text and pack_size_quantity not in (None, "") and pack_size_unit not in (None, ""):
        normalized_pack_size_text = f"{_format_quantity(pack_size_quantity)} {pack_size_unit}"
    normalized_uom = _normalize_uom(unit_of_measurement)
    normalized_count_type = _normalize_count_type(count_type)
    normalized_quantity = _calculate_normalized_quantity(
        count_each_quantity=normalized_each_quantity,
        count_case_quantity=normalized_case_quantity,
        pack_quantity=normalized_pack_quantity,
        unit_of_measurement=normalized_uom,
        count_type=normalized_count_type,
    )
    normalized_unit = _storage_unit_for_uom(normalized_uom)
    if unit:
        normalized_unit = _normalize_inventory_unit(unit)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT status
            FROM inventory_location
            WHERE inventory_location_id = ?
            """,
            (location_id,),
        )
        location_row = cursor.fetchone()
        if location_row is None:
            raise InvalidInventoryError("Inventory location not found.")
        if location_row[0] != "active":
            raise InvalidInventoryError("Inventory location is inactive.")

        cursor.execute(
            """
            SELECT item_name, item_type, status
            FROM item
            WHERE item_id = ?
            """,
            (normalized_item_id,),
        )
        item_row = cursor.fetchone()
        if item_row is None or item_row[2] != "live" or item_row[1] != "base_food":
            raise InvalidInventoryError("Inventory counts can only use live base food items.")
        catalog_item_id = ensure_legacy_inventory_match_for_item_with_cursor(
            cursor=cursor,
            recipe_collection_item_id=normalized_item_id,
            display_name=item_row[0],
            pack_quantity=normalized_pack_quantity,
            pack_size_text=normalized_pack_size_text,
            purchase_uom=normalized_uom,
        )

        cursor.execute(
            """
            INSERT INTO inventory_location_item (
                inventory_location_id,
                item_id,
                inventory_catalog_item_id,
                quantity,
                unit,
                count_each_quantity,
                count_case_quantity,
                pack_quantity,
                pack_size_text,
                unit_of_measurement,
                count_type,
                display_sequence,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(inventory_location_id, item_id) DO UPDATE SET
                inventory_catalog_item_id = excluded.inventory_catalog_item_id,
                quantity = excluded.quantity,
                unit = excluded.unit,
                count_each_quantity = excluded.count_each_quantity,
                count_case_quantity = excluded.count_case_quantity,
                pack_quantity = excluded.pack_quantity,
                pack_size_text = excluded.pack_size_text,
                unit_of_measurement = excluded.unit_of_measurement,
                count_type = excluded.count_type,
                updated_at = datetime('now')
            """,
            (
                location_id,
                normalized_item_id,
                catalog_item_id,
                normalized_quantity,
                normalized_unit,
                normalized_each_quantity,
                normalized_case_quantity,
                normalized_pack_quantity,
                normalized_pack_size_text,
                normalized_uom,
                normalized_count_type,
                _next_display_sequence(cursor, location_id),
            ),
        )
        cursor.execute(
            """
            UPDATE inventory_location
            SET updated_at = datetime('now')
            WHERE inventory_location_id = ?
            """,
            (location_id,),
        )
        conn.commit()

    return {
        "item_id": normalized_item_id,
        "item_name": item_row[0],
        "quantity": normalized_quantity,
        "quantity_display": _format_quantity(normalized_quantity),
        "unit": normalized_unit,
        "unit_label": format_unit_label(normalized_unit),
    }


def update_inventory_location_item(
    *,
    inventory_location_item_id,
    quantity=None,
    unit=None,
    count_each_quantity=None,
    count_case_quantity=None,
    pack_quantity=None,
    pack_size_text=None,
    unit_of_measurement="Case",
    count_type="counted_by_each_only",
    pack_size_quantity=None,
    pack_size_unit=None,
) -> None:
    initialize_database()
    try:
        row_id = int(inventory_location_item_id)
    except (TypeError, ValueError):
        raise InvalidInventoryError("Inventory item row not found.")
    normalized_each_quantity = _normalize_quantity(
        count_each_quantity if count_each_quantity is not None else quantity or 0,
        allow_blank=True,
    ) or 0
    normalized_case_quantity = _normalize_quantity(count_case_quantity, allow_blank=True) or 0
    normalized_pack_quantity = _normalize_optional_pack_quantity(
        pack_quantity if pack_quantity not in (None, "") else pack_size_quantity
    )
    normalized_pack_size_text = _normalize_pack_size_text(pack_size_text)
    if not normalized_pack_size_text and pack_size_quantity not in (None, "") and pack_size_unit not in (None, ""):
        normalized_pack_size_text = f"{_format_quantity(pack_size_quantity)} {pack_size_unit}"
    normalized_uom = _normalize_uom(unit_of_measurement)
    normalized_count_type = _normalize_count_type(count_type)
    normalized_quantity = _calculate_normalized_quantity(
        count_each_quantity=normalized_each_quantity,
        count_case_quantity=normalized_case_quantity,
        pack_quantity=normalized_pack_quantity,
        unit_of_measurement=normalized_uom,
        count_type=normalized_count_type,
    )
    normalized_unit = _storage_unit_for_uom(normalized_uom)
    if unit:
        normalized_unit = _normalize_inventory_unit(unit)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ili.item_id, i.item_name
            FROM inventory_location_item ili
            JOIN item i
              ON i.item_id = ili.item_id
            WHERE ili.inventory_location_item_id = ?
            """,
            (row_id,),
        )
        item_row = cursor.fetchone()
        if item_row is None:
            raise InvalidInventoryError("Inventory item row not found.")
        catalog_item_id = ensure_legacy_inventory_match_for_item_with_cursor(
            cursor=cursor,
            recipe_collection_item_id=int(item_row[0]),
            display_name=item_row[1],
            pack_quantity=normalized_pack_quantity,
            pack_size_text=normalized_pack_size_text,
            purchase_uom=normalized_uom,
        )

        cursor.execute(
            """
            UPDATE inventory_location_item
            SET quantity = ?,
                inventory_catalog_item_id = ?,
                unit = ?,
                count_each_quantity = ?,
                count_case_quantity = ?,
                pack_quantity = ?,
                pack_size_text = ?,
                unit_of_measurement = ?,
                count_type = ?,
                updated_at = datetime('now')
            WHERE inventory_location_item_id = ?
            """,
            (
                normalized_quantity,
                catalog_item_id,
                normalized_unit,
                normalized_each_quantity,
                normalized_case_quantity,
                normalized_pack_quantity,
                normalized_pack_size_text,
                normalized_uom,
                normalized_count_type,
                row_id,
            ),
        )
        if cursor.rowcount == 0:
            raise InvalidInventoryError("Inventory item row not found.")
        cursor.execute(
            """
            UPDATE inventory_location
            SET updated_at = datetime('now')
            WHERE inventory_location_id = (
                SELECT inventory_location_id
                FROM inventory_location_item
                WHERE inventory_location_item_id = ?
            )
            """,
            (row_id,),
        )
        conn.commit()


def delete_inventory_location_item(*, inventory_location_item_id) -> None:
    initialize_database()
    try:
        row_id = int(inventory_location_item_id)
    except (TypeError, ValueError):
        raise InvalidInventoryError("Inventory item row not found.")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM inventory_location_item WHERE inventory_location_item_id = ?",
            (row_id,),
        )
        if cursor.rowcount == 0:
            raise InvalidInventoryError("Inventory item row not found.")
        conn.commit()


def add_inventory_location_break(*, inventory_location_id, break_label: str) -> int:
    initialize_database()
    try:
        location_id = int(inventory_location_id)
    except (TypeError, ValueError):
        raise InvalidInventoryError("Inventory location not found.")
    normalized_label = _normalize_name(break_label, "Break label")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status FROM inventory_location WHERE inventory_location_id = ?",
            (location_id,),
        )
        location_row = cursor.fetchone()
        if location_row is None:
            raise InvalidInventoryError("Inventory location not found.")
        cursor.execute(
            """
            INSERT INTO inventory_location_break (
                inventory_location_id,
                break_label,
                display_sequence,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, datetime('now'), datetime('now'))
            """,
            (location_id, normalized_label, _next_display_sequence(cursor, location_id)),
        )
        break_id = int(cursor.lastrowid)
        conn.commit()
        return break_id


def delete_inventory_location_break(*, inventory_location_break_id) -> None:
    initialize_database()
    try:
        break_id = int(inventory_location_break_id)
    except (TypeError, ValueError):
        raise InvalidInventoryError("Break line not found.")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM inventory_location_break WHERE inventory_location_break_id = ?",
            (break_id,),
        )
        if cursor.rowcount == 0:
            raise InvalidInventoryError("Break line not found.")
        conn.commit()


def _get_count_row(cursor, *, row_type: str, row_id: int) -> dict:
    if row_type == "item":
        cursor.execute(
            """
            SELECT inventory_location_item_id, inventory_location_id, display_sequence
            FROM inventory_location_item
            WHERE inventory_location_item_id = ?
            """,
            (row_id,),
        )
    elif row_type == "break":
        cursor.execute(
            """
            SELECT inventory_location_break_id, inventory_location_id, display_sequence
            FROM inventory_location_break
            WHERE inventory_location_break_id = ?
            """,
            (row_id,),
        )
    else:
        raise InvalidInventoryError("Count row type is invalid.")
    row = cursor.fetchone()
    if row is None:
        raise InvalidInventoryError("Count row not found.")
    return {
        "row_type": row_type,
        "row_id": int(row[0]),
        "inventory_location_id": int(row[1]),
        "display_sequence": int(row[2] or 0),
    }


def _update_count_row_sequence(cursor, row: dict, display_sequence: int) -> None:
    table = "inventory_location_item" if row["row_type"] == "item" else "inventory_location_break"
    id_column = "inventory_location_item_id" if row["row_type"] == "item" else "inventory_location_break_id"
    cursor.execute(
        f"UPDATE {table} SET display_sequence = ?, updated_at = datetime('now') WHERE {id_column} = ?",
        (display_sequence, row["row_id"]),
    )


def move_inventory_count_row(*, row_type: str, row_id, direction: str) -> None:
    initialize_database()
    try:
        normalized_row_id = int(row_id)
    except (TypeError, ValueError):
        raise InvalidInventoryError("Count row not found.")
    if direction not in {"up", "down"}:
        raise InvalidInventoryError("Move direction is invalid.")

    with get_connection() as conn:
        cursor = conn.cursor()
        selected_row = _get_count_row(cursor, row_type=row_type, row_id=normalized_row_id)
        count_rows = list_inventory_location_count_rows(selected_row["inventory_location_id"])
        key = "inventory_location_item_id" if row_type == "item" else "inventory_location_break_id"
        current_index = next(
            (
                index
                for index, row in enumerate(count_rows)
                if row["row_type"] == row_type and row.get(key) == normalized_row_id
            ),
            None,
        )
        if current_index is None:
            raise InvalidInventoryError("Count row not found.")
        swap_index = current_index - 1 if direction == "up" else current_index + 1
        if swap_index < 0 or swap_index >= len(count_rows):
            return
        swap_row_data = count_rows[swap_index]
        swap_key = "inventory_location_item_id" if swap_row_data["row_type"] == "item" else "inventory_location_break_id"
        swap_row = _get_count_row(cursor, row_type=swap_row_data["row_type"], row_id=swap_row_data[swap_key])
        _update_count_row_sequence(cursor, selected_row, swap_row["display_sequence"])
        _update_count_row_sequence(cursor, swap_row, selected_row["display_sequence"])
        conn.commit()


def transfer_inventory_location_item(*, inventory_location_item_id, target_inventory_location_id) -> None:
    initialize_database()
    try:
        row_id = int(inventory_location_item_id)
        target_location_id = int(target_inventory_location_id)
    except (TypeError, ValueError):
        raise InvalidInventoryError("Transfer target is invalid.")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT inventory_location_id, item_id
            FROM inventory_location_item
            WHERE inventory_location_item_id = ?
            """,
            (row_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise InvalidInventoryError("Inventory item row not found.")
        current_location_id = int(row[0])
        item_id = int(row[1])
        if current_location_id == target_location_id:
            return
        cursor.execute(
            "SELECT status FROM inventory_location WHERE inventory_location_id = ?",
            (target_location_id,),
        )
        target_row = cursor.fetchone()
        if target_row is None or target_row[0] != "active":
            raise InvalidInventoryError("Transfer target location is not active.")
        cursor.execute(
            """
            SELECT inventory_location_item_id
            FROM inventory_location_item
            WHERE inventory_location_id = ?
              AND item_id = ?
            """,
            (target_location_id, item_id),
        )
        if cursor.fetchone() is not None:
            raise InvalidInventoryError("That item already exists in the target location.")
        cursor.execute(
            """
            UPDATE inventory_location_item
            SET inventory_location_id = ?,
                display_sequence = ?,
                updated_at = datetime('now')
            WHERE inventory_location_item_id = ?
            """,
            (target_location_id, _next_display_sequence(cursor, target_location_id), row_id),
        )
        conn.commit()


def _list_current_on_hand() -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                i.item_id,
                i.item_name,
                i.item_type,
                i.item_category,
                ili.unit,
                SUM(ili.quantity),
                COUNT(DISTINCT ili.inventory_location_id),
                MAX(ili.updated_at),
                MAX(ili.pack_quantity),
                MAX(ili.unit_of_measurement),
                SUM(ili.count_each_quantity),
                SUM(ili.count_case_quantity),
                SUM(
                    CASE
                        WHEN ili.unit_of_measurement = 'Case' AND ili.pack_quantity IS NOT NULL AND ili.pack_quantity > 0
                        THEN ili.count_case_quantity + (ili.count_each_quantity / ili.pack_quantity)
                        ELSE NULL
                    END
                ),
                SUM(
                    CASE
                        WHEN ili.unit_of_measurement = 'Case' AND ili.pack_quantity IS NOT NULL AND ili.pack_quantity > 0
                        THEN (ili.count_case_quantity * ili.pack_quantity) + ili.count_each_quantity
                        ELSE NULL
                    END
                )
            FROM inventory_location_item ili
            JOIN inventory_location il
              ON il.inventory_location_id = ili.inventory_location_id
            JOIN item i
              ON i.item_id = ili.item_id
            WHERE il.status = 'active'
            GROUP BY i.item_id, ili.unit, ili.unit_of_measurement
            ORDER BY i.item_name ASC, ili.unit ASC
            """
        )
        rows = []
        for row in cursor.fetchall():
            payload = {
                "item_id": int(row[0]),
                "item_name": row[1],
                "item_type": row[2],
                "item_category": row[3],
                "item_category_label": ITEM_CATEGORY_LABELS.get(row[3], str(row[3]).title()),
                "unit": row[4],
                "unit_label": format_unit_label(row[4]),
                "quantity": float(row[5] or 0),
                "quantity_display": _format_quantity(row[5]),
                "location_count": int(row[6] or 0),
                "last_counted_at": row[7] or "",
                "pack_quantity": row[8],
                "unit_of_measurement": row[9],
                "count_each_quantity": float(row[10] or 0),
                "count_case_quantity": float(row[11] or 0),
                "case_quantity": row[12],
                "each_quantity": row[13],
            }
            payload.update(_format_current_on_hand_display(payload))
            rows.append(payload)
        return rows


def get_inventory_dashboard() -> dict:
    initialize_database()
    locations = list_inventory_locations(include_inactive=True)
    current_on_hand = _list_current_on_hand()
    from services.inventory_usage_service import get_inventory_item_count_rolldown, get_inventory_item_usage

    for item in current_on_hand:
        usage = get_inventory_item_usage(item["item_id"], limit=5)
        item["usage_summary"] = usage
        item["count_rolldown"] = get_inventory_item_count_rolldown(item["item_id"])
    location_tree = get_inventory_location_tree()
    return {
        "locations": locations,
        "location_tree": location_tree,
        "active_locations": [location for location in locations if location["status"] == "active"],
        "current_on_hand": current_on_hand,
        "totals": {
            "location_count": len([location for location in locations if location["parent_inventory_location_id"] is None]),
            "sub_location_count": len([location for location in locations if location["parent_inventory_location_id"] is not None]),
            "active_location_count": len(
                [
                    location
                    for location in locations
                    if location["status"] == "active" and location["parent_inventory_location_id"] is None
                ]
            ),
            "active_sub_location_count": len(
                [
                    location
                    for location in locations
                    if location["status"] == "active" and location["parent_inventory_location_id"] is not None
                ]
            ),
            "current_item_count": len(current_on_hand),
        },
        "unit_options": [
            {"value": unit, "label": format_unit_label(unit)}
            for unit in STANDARD_UNITS
        ],
        "unit_of_measurement_options": list(INVENTORY_UOM_OPTIONS),
        "count_type_options": [
            {"value": value, "label": label.title()}
            for value, label in INVENTORY_COUNT_TYPES.items()
        ],
    }


def list_live_inventory_items(limit: int = 250) -> list[dict]:
    initialize_database()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT item_id, item_name, item_type
            FROM item
            WHERE status = 'live'
              AND item_type = 'base_food'
            ORDER BY item_name ASC, item_id ASC
            LIMIT ?
            """,
            (limit,),
        )
        return [
            {
                "item_id": int(row[0]),
                "item_name": row[1],
                "item_type": row[2],
            }
            for row in cursor.fetchall()
        ]
