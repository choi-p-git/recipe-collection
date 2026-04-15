from db import get_connection
from services.unit_conversion_service import (
    convert_unit_value,
    convert_with_item_mass_volume_bridge,
)


ACCORDING_TO_TASTE_THRESHOLD = 0.001


def _format_flattened_quantity(quantity: float) -> str:
    rounded_quantity = round(quantity, 3)
    if rounded_quantity < ACCORDING_TO_TASTE_THRESHOLD:
        return "according to taste"
    return f"{rounded_quantity:g}"


def _build_measurement_equivalent(
    *,
    quantity: float,
    source_unit: str,
    item_type: str,
    target_measurement_type: str | None,
    mass_quantity: float | None,
    mass_unit: str | None,
    volume_quantity: float | None,
    volume_unit: str | None,
) -> dict | None:
    if target_measurement_type == "mass" and mass_unit:
        result = convert_unit_value(quantity=quantity, from_unit=source_unit, to_unit=mass_unit)
        if not result["ok"]:
            result = convert_with_item_mass_volume_bridge(
                quantity=quantity,
                from_unit=source_unit,
                to_unit=mass_unit,
                item_type=item_type,
                mass_quantity=mass_quantity,
                mass_unit=mass_unit,
                volume_quantity=volume_quantity,
                volume_unit=volume_unit,
            )
        if result["ok"]:
            return {
                "quantity": float(result["quantity"]),
                "quantity_display": _format_flattened_quantity(float(result["quantity"])),
                "unit": mass_unit,
                "label": "Official mass equivalent",
                "status": result["status"],
            }

    if target_measurement_type == "volume" and volume_unit:
        result = convert_unit_value(quantity=quantity, from_unit=source_unit, to_unit=volume_unit)
        if not result["ok"]:
            result = convert_with_item_mass_volume_bridge(
                quantity=quantity,
                from_unit=source_unit,
                to_unit=volume_unit,
                item_type=item_type,
                mass_quantity=mass_quantity,
                mass_unit=mass_unit,
                volume_quantity=volume_quantity,
                volume_unit=volume_unit,
            )
        if result["ok"]:
            return {
                "quantity": float(result["quantity"]),
                "quantity_display": _format_flattened_quantity(float(result["quantity"])),
                "unit": volume_unit,
                "label": "Official volume equivalent",
                "status": result["status"],
            }

    return None


def build_flattened_recipe_view(
    recipe_item_id: int,
    scale_factor: float = 1.0,
    preferred_measurement_type: str | None = None,
) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT item_id, item_name, item_type, status
            FROM item
            WHERE item_id = ?
            """,
            (recipe_item_id,),
        )
        root_row = cursor.fetchone()

        if root_row is None or root_row[2] != "recipe":
            return {"available": False, "rows": [], "warnings": []}

        flattened_rows: list[dict] = []
        warnings: list[str] = []

        def warn_once(message: str) -> None:
            if message not in warnings:
                warnings.append(message)

        def get_components(parent_recipe_item_id: int) -> list[tuple]:
            cursor.execute(
                """
                SELECT
                    rc.component_item_id,
                    i.item_name,
                    i.item_type,
                    i.status,
                    i.yield_quantity,
                    i.yield_unit,
                    i.mass_quantity,
                    i.mass_unit,
                    i.volume_quantity,
                    i.volume_unit,
                    rc.component_quantity,
                    rc.component_unit
                FROM recipe_component rc
                JOIN item i
                  ON rc.component_item_id = i.item_id
                WHERE rc.parent_recipe_item_id = ?
                ORDER BY rc.component_sequence ASC, rc.recipe_component_id ASC
                """,
                (parent_recipe_item_id,),
            )
            return cursor.fetchall()

        def flatten_branch(
            current_recipe_id: int,
            current_recipe_name: str,
            scale_factor: float,
            path_ids: list[int],
            path_names: list[str],
            depth: int,
        ) -> None:
            for component in get_components(current_recipe_id):
                (
                    component_item_id,
                    component_item_name,
                    component_item_type,
                    component_status,
                    component_yield_quantity,
                    component_yield_unit,
                    component_mass_quantity,
                    component_mass_unit,
                    component_volume_quantity,
                    component_volume_unit,
                    component_quantity,
                    component_unit,
                ) = component

                scaled_quantity = float(component_quantity) * scale_factor
                equivalent = _build_measurement_equivalent(
                    quantity=scaled_quantity,
                    source_unit=component_unit,
                    item_type=component_item_type,
                    target_measurement_type=preferred_measurement_type,
                    mass_quantity=component_mass_quantity,
                    mass_unit=component_mass_unit,
                    volume_quantity=component_volume_quantity,
                    volume_unit=component_volume_unit,
                )

                if component_item_type == "base_food":
                    flattened_rows.append(
                        {
                            "row_type": "base_food",
                            "depth": depth,
                            "component_item_id": int(component_item_id),
                            "component_item_name": component_item_name,
                            "component_item_type": "base_food",
                            "mass_quantity": component_mass_quantity,
                            "mass_unit": component_mass_unit,
                            "volume_quantity": component_volume_quantity,
                            "volume_unit": component_volume_unit,
                            "component_unit": component_unit,
                            "total_quantity": scaled_quantity,
                            "quantity_display": _format_flattened_quantity(scaled_quantity),
                            "source_recipe_name": current_recipe_name,
                            "measurement_equivalent": equivalent,
                        }
                    )
                    continue

                if int(component_item_id) in path_ids:
                    warn_once(
                        "Cycle detected while flattening: "
                        + " -> ".join([*path_names, component_item_name])
                    )
                    continue

                if component_status != "live":
                    warn_once(
                        f"Sub-recipe '{component_item_name}' was not flattened because it is not live."
                    )
                    continue

                if not component_yield_quantity or not component_yield_unit:
                    warn_once(
                        f"Sub-recipe '{component_item_name}' is missing yield data and could not be flattened."
                    )
                    continue

                child_quantity_for_scale = scaled_quantity
                component_unit_label = str(component_unit).strip()
                yield_unit_label = str(component_yield_unit).strip()

                if component_unit_label != yield_unit_label:
                    conversion_result = convert_unit_value(
                        quantity=scaled_quantity,
                        from_unit=component_unit_label,
                        to_unit=yield_unit_label,
                    )
                    if not conversion_result["ok"]:
                        warn_once(
                            f"Sub-recipe '{component_item_name}' could not be flattened because component unit "
                            f"'{component_unit}' is not convertible to recipe yield unit '{component_yield_unit}'."
                        )
                        continue
                    child_quantity_for_scale = float(conversion_result["quantity"])

                child_scale = child_quantity_for_scale / float(component_yield_quantity)
                flattened_rows.append(
                    {
                        "row_type": "sub_recipe",
                        "depth": depth,
                        "component_item_id": int(component_item_id),
                        "component_item_name": component_item_name,
                        "component_item_type": "recipe",
                        "mass_quantity": component_mass_quantity,
                        "mass_unit": component_mass_unit,
                        "volume_quantity": component_volume_quantity,
                        "volume_unit": component_volume_unit,
                        "component_unit": component_unit,
                        "total_quantity": scaled_quantity,
                        "quantity_display": _format_flattened_quantity(scaled_quantity),
                        "source_recipe_name": current_recipe_name,
                        "child_yield_quantity": component_yield_quantity,
                        "child_yield_unit": component_yield_unit,
                        "measurement_equivalent": equivalent,
                    }
                )
                flatten_branch(
                    current_recipe_id=int(component_item_id),
                    current_recipe_name=component_item_name,
                    scale_factor=child_scale,
                    path_ids=[*path_ids, int(component_item_id)],
                    path_names=[*path_names, component_item_name],
                    depth=depth + 1,
                )

        flatten_branch(
            current_recipe_id=int(root_row[0]),
            current_recipe_name=root_row[1],
            scale_factor=scale_factor,
            path_ids=[int(root_row[0])],
            path_names=[root_row[1]],
            depth=0,
        )

    return {
        "available": root_row[3] == "live",
        "rows": flattened_rows,
        "warnings": warnings,
    }
