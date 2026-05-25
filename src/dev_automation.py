from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence

from config.menu_builder import CONCEPT_OPTIONS, DAY_OF_WEEK_OPTIONS, MEAL_PERIOD_OPTIONS
from db import get_connection, initialize_database
from queries.menu_forecast import get_menu_forecast_page
from services.menu_forecast_service import save_menu_forecast_yield
from services.menu_service import create_menu, replace_menu_slot_items
from services.production_record_service import (
    ensure_production_record,
    post_production_record,
    save_production_record_line,
)


DEV_AUTOMATION_USER_ID = "dev_user_001"
DEV_AUTOMATION_DISPLAY_NAME = "Plato Choi"
DEFAULT_SERVICE_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]
DEFAULT_MEAL_PERIODS = ["breakfast", "dinner"]
DEFAULT_CONCEPTS = ["hot_line", "cold_line", "grab_go"]
DEFAULT_WEEKS = 8
DEFAULT_MIN_ITEMS = 3
DEFAULT_MAX_ITEMS = 5
DEFAULT_RANDOM_SEED = 42


@dataclass(frozen=True)
class AutomationConfig:
    menu_name: str = "Dev Automation Draft Menu"
    start_date: date | None = None
    weeks: int = DEFAULT_WEEKS
    service_days: tuple[str, ...] = tuple(DEFAULT_SERVICE_DAYS)
    meal_periods: tuple[str, ...] = tuple(DEFAULT_MEAL_PERIODS)
    concepts: tuple[str, ...] = tuple(DEFAULT_CONCEPTS)
    min_items_per_slot: int = DEFAULT_MIN_ITEMS
    max_items_per_slot: int = DEFAULT_MAX_ITEMS
    random_seed: int = DEFAULT_RANDOM_SEED
    post_records: bool = False
    actor_user_id: str = DEV_AUTOMATION_USER_ID
    actor_display_name: str = DEV_AUTOMATION_DISPLAY_NAME


def _allowed_values(options: list[dict[str, str]]) -> list[str]:
    return [option["value"] for option in options]


def _next_monday(today: date | None = None) -> date:
    reference = today or date.today()
    days_until_monday = (7 - reference.weekday()) % 7
    return reference + timedelta(days=days_until_monday)


def _menu_end_date(start_date: date, weeks: int) -> date:
    return start_date + timedelta(days=(weeks * 7) - 1)


def _normalize_csv_values(value: str | None, *, defaults: Sequence[str], allowed: set[str]) -> tuple[str, ...]:
    if not value:
        return tuple(defaults)
    normalized = []
    seen = set()
    for part in value.split(","):
        item = part.strip().lower()
        if item in allowed and item not in seen:
            normalized.append(item)
            seen.add(item)
    return tuple(normalized or defaults)


def _load_live_menu_items() -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                item_id,
                item_name,
                item_type,
                yield_quantity,
                yield_unit,
                mass_quantity,
                mass_unit,
                volume_quantity,
                volume_unit
            FROM item
            WHERE status = 'live'
              AND item_type IN ('recipe', 'base_food')
            ORDER BY item_type DESC, item_name ASC, item_id ASC
            """
        )
        return [
            {
                "item_id": int(row[0]),
                "item_name": row[1],
                "item_type": row[2],
                "yield_quantity": row[3],
                "yield_unit": row[4] or "",
                "mass_quantity": row[5],
                "mass_unit": row[6] or "",
                "volume_quantity": row[7],
                "volume_unit": row[8] or "",
            }
            for row in cursor.fetchall()
        ]


def _load_menu_slots(menu_id: int) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT menu_slot_id, week_number, day_of_week, meal_period, concept_name
            FROM menu_slot
            WHERE menu_id = ?
            ORDER BY week_number ASC, menu_slot_id ASC
            """,
            (menu_id,),
        )
        return [
            {
                "menu_slot_id": int(row[0]),
                "week_number": int(row[1]),
                "day_of_week": row[2],
                "meal_period": row[3],
                "concept_name": row[4],
            }
            for row in cursor.fetchall()
        ]


def _load_menu_slot_items(menu_id: int) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                msi.menu_slot_item_id,
                msi.item_id,
                i.item_name,
                i.item_type,
                i.yield_unit,
                i.mass_unit,
                i.volume_unit
            FROM menu_slot_item msi
            JOIN menu_slot ms
              ON ms.menu_slot_id = msi.menu_slot_id
            JOIN item i
              ON i.item_id = msi.item_id
            WHERE ms.menu_id = ?
            ORDER BY ms.week_number ASC, ms.menu_slot_id ASC, msi.item_sequence ASC
            """,
            (menu_id,),
        )
        return [
            {
                "menu_slot_item_id": int(row[0]),
                "item_id": int(row[1]),
                "item_name": row[2],
                "item_type": row[3],
                "yield_unit": row[4] or "",
                "mass_unit": row[5] or "",
                "volume_unit": row[6] or "",
            }
            for row in cursor.fetchall()
        ]


def _choose_slot_items(
    *,
    rng: random.Random,
    live_items: list[dict],
    min_items: int,
    max_items: int,
) -> list[int]:
    recipes = [item for item in live_items if item["item_type"] == "recipe"]
    base_foods = [item for item in live_items if item["item_type"] == "base_food"]
    count = rng.randint(min_items, max_items)
    selected: list[dict] = []

    if recipes:
        selected.append(rng.choice(recipes))
    if base_foods and count > 1:
        selected.append(rng.choice(base_foods))

    remaining_pool = [item for item in live_items if item["item_id"] not in {row["item_id"] for row in selected}]
    if remaining_pool:
        selected.extend(rng.sample(remaining_pool, k=min(count - len(selected), len(remaining_pool))))

    return [item["item_id"] for item in selected[:count]]


def _forecast_unit_options(slot_item: dict) -> list[str]:
    if slot_item.get("item_type") == "recipe":
        options = [
            slot_item.get("yield_unit"),
            slot_item.get("mass_unit"),
            slot_item.get("volume_unit"),
        ]
    else:
        options = [
            slot_item.get("mass_unit"),
            slot_item.get("volume_unit"),
            slot_item.get("yield_unit"),
            "each",
        ]
    normalized = []
    for unit in options:
        if unit and unit not in normalized:
            normalized.append(unit)
    return normalized or ["each"]


def _random_forecast_quantity(rng: random.Random, unit: str) -> float:
    if unit in {"each"}:
        return float(rng.randint(24, 420))
    if unit in {"g", "ml"}:
        return round(rng.uniform(250, 12000), 2)
    if unit in {"kg", "L"}:
        return round(rng.uniform(2, 40), 2)
    if unit in {"oz", "cup"}:
        return round(rng.uniform(12, 320), 2)
    if unit in {"lb", "qt"}:
        return round(rng.uniform(4, 120), 2)
    if unit in {"pt", "tsp", "tbs"}:
        return round(rng.uniform(10, 240), 2)
    if unit == "gal":
        return round(rng.uniform(1, 24), 2)
    return round(rng.uniform(5, 100), 2)


def _production_scenario_values(rng: random.Random, forecast_quantity: float) -> dict:
    roll = rng.random()
    direction = rng.choice([-1, 1])
    if roll < 0.50:
        variance_percent = direction * rng.uniform(0, 0.049)
    elif roll < 0.70:
        variance_percent = direction * rng.uniform(0.05, 0.10)
    elif roll < 0.90:
        variance_percent = direction * rng.uniform(0.10, 0.15)
    else:
        variance_percent = direction * 0.20

    absolute_percent = abs(variance_percent)
    if absolute_percent < 0.05:
        scenario = "accurate"
        reason_code = "as_expected"
    elif absolute_percent < 0.15:
        scenario = "review"
        reason_code = rng.choice(["menu_mix", "weather", "field_trip"])
    else:
        scenario = "miss"
        reason_code = rng.choice(["extra_guests", "unexpected_low_attendance", "sports_team_away"])

    actual_quantity = max(0.0, forecast_quantity)
    variance_quantity = forecast_quantity * variance_percent
    return {
        "scenario": scenario,
        "actual_quantity": round(actual_quantity, 3),
        "variance_quantity": round(variance_quantity, 3),
        "variance_percent": round(variance_percent * 100, 3),
        "reason_code": reason_code,
    }


def run_dev_menu_automation(config: AutomationConfig | None = None) -> dict:
    config = config or AutomationConfig()
    if config.weeks <= 0:
        raise ValueError("weeks must be greater than zero.")
    if config.min_items_per_slot <= 0 or config.max_items_per_slot < config.min_items_per_slot:
        raise ValueError("item range must be positive and min cannot exceed max.")

    rng = random.Random(config.random_seed)
    initialize_database(seed=True)
    live_items = _load_live_menu_items()
    if not live_items:
        raise ValueError("No live recipes or base foods are available for automation.")
    if len(live_items) < config.min_items_per_slot:
        raise ValueError("Not enough live items are available for the requested slot size.")

    start_date = config.start_date or _next_monday()
    end_date = _menu_end_date(start_date, config.weeks)
    menu_id = create_menu(
        menu_name=config.menu_name,
        author_user_id=config.actor_user_id,
        author_display_name=config.actor_display_name,
        service_days=list(config.service_days),
        meal_periods=list(config.meal_periods),
        concepts=list(config.concepts),
        menu_length_weeks=config.weeks,
        menu_start_date=start_date.isoformat(),
        menu_end_date=end_date.isoformat(),
        require_date_range=True,
        allowed_service_days=_allowed_values(DAY_OF_WEEK_OPTIONS),
        allowed_meal_periods=_allowed_values(MEAL_PERIOD_OPTIONS),
        allowed_concepts=_allowed_values(CONCEPT_OPTIONS),
    )

    slots = _load_menu_slots(menu_id)
    assignment_count = 0
    for slot in slots:
        item_ids = _choose_slot_items(
            rng=rng,
            live_items=live_items,
            min_items=config.min_items_per_slot,
            max_items=config.max_items_per_slot,
        )
        replace_menu_slot_items(
            menu_slot_id=slot["menu_slot_id"],
            selected_item_ids=item_ids,
            actor_user_id=config.actor_user_id,
        )
        assignment_count += len(item_ids)

    forecast_count = 0
    for slot_item in _load_menu_slot_items(menu_id):
        unit = rng.choice(_forecast_unit_options(slot_item))
        save_menu_forecast_yield(
            menu_id=menu_id,
            menu_slot_item_id=slot_item["menu_slot_item_id"],
            actor_user_id=config.actor_user_id,
            forecast_yield_quantity=_random_forecast_quantity(rng, unit),
            forecast_yield_unit=unit,
        )
        forecast_count += 1

    record_count = 0
    posted_record_count = 0
    line_count = 0
    scenario_counts = {"accurate": 0, "review": 0, "miss": 0}
    for week_number in range(1, config.weeks + 1):
        for day_of_week in config.service_days:
            forecast_page = get_menu_forecast_page(
                menu_id,
                week_number=week_number,
                day_of_week=day_of_week,
            )
            if forecast_page is None:
                continue
            record = ensure_production_record(
                menu_id=menu_id,
                week_number=week_number,
                day_of_week=day_of_week,
                production_summary=forecast_page["production_summary"],
                actor_user_id=config.actor_user_id,
            )
            record_count += 1
            for line in record["lines"]:
                scenario = _production_scenario_values(
                    rng,
                    float(line["forecast_quantity"] or 0),
                )
                save_production_record_line(
                    menu_id=menu_id,
                    production_record_line_id=line["production_record_line_id"],
                    actor_user_id=config.actor_user_id,
                    actual_quantity=str(scenario["actual_quantity"]),
                    actual_unit=line["forecast_unit"],
                    end_service_variance_quantity=str(scenario["variance_quantity"]),
                    end_service_variance_unit=line["forecast_unit"],
                    reason_code=scenario["reason_code"],
                    notes=f"Dev automation scenario: {scenario['scenario']}",
                )
                scenario_counts[scenario["scenario"]] += 1
                line_count += 1
            if config.post_records:
                post_production_record(
                    menu_id=menu_id,
                    production_record_id=record["production_record_id"],
                    actor_user_id=config.actor_user_id,
                )
                posted_record_count += 1

    return {
        "menu_id": menu_id,
        "menu_name": config.menu_name,
        "menu_start_date": start_date.isoformat(),
        "menu_end_date": end_date.isoformat(),
        "weeks": config.weeks,
        "slot_count": len(slots),
        "assignment_count": assignment_count,
        "forecast_count": forecast_count,
        "production_record_count": record_count,
        "posted_record_count": posted_record_count,
        "draft_record_count": record_count - posted_record_count,
        "production_record_line_count": line_count,
        "scenario_counts": scenario_counts,
        "random_seed": config.random_seed,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create randomized draft dev menu, forecast, and production records.")
    parser.add_argument("--menu-name", default="Dev Automation Draft Menu")
    parser.add_argument("--start-date", help="Menu start date in YYYY-MM-DD format. Defaults to the next Monday.")
    parser.add_argument("--weeks", type=int, default=DEFAULT_WEEKS)
    parser.add_argument("--service-days", help="Comma-separated days. Defaults to monday-friday.")
    parser.add_argument("--meal-periods", help="Comma-separated meal periods. Defaults to breakfast,dinner.")
    parser.add_argument("--concepts", help="Comma-separated concepts. Defaults to hot_line,cold_line,grab_go.")
    parser.add_argument("--min-items", type=int, default=DEFAULT_MIN_ITEMS)
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS)
    parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED)
    parser.add_argument("--post-records", action="store_true", help="Post and lock generated production records.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    allowed_days = set(_allowed_values(DAY_OF_WEEK_OPTIONS))
    allowed_meals = set(_allowed_values(MEAL_PERIOD_OPTIONS))
    allowed_concepts = set(_allowed_values(CONCEPT_OPTIONS))
    config = AutomationConfig(
        menu_name=args.menu_name,
        start_date=date.fromisoformat(args.start_date) if args.start_date else None,
        weeks=args.weeks,
        service_days=_normalize_csv_values(args.service_days, defaults=DEFAULT_SERVICE_DAYS, allowed=allowed_days),
        meal_periods=_normalize_csv_values(args.meal_periods, defaults=DEFAULT_MEAL_PERIODS, allowed=allowed_meals),
        concepts=_normalize_csv_values(args.concepts, defaults=DEFAULT_CONCEPTS, allowed=allowed_concepts),
        min_items_per_slot=args.min_items,
        max_items_per_slot=args.max_items,
        random_seed=args.seed,
        post_records=args.post_records,
    )
    print(json.dumps(run_dev_menu_automation(config), indent=2))


if __name__ == "__main__":
    main()
