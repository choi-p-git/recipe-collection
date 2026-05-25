from services.production_record_service import _build_history_report


def _history_line(item_id: int, name: str, variance: float) -> dict:
    return {
        "item_id": item_id,
        "recipe_name": name,
        "end_service_variance_quantity": variance,
        "end_service_variance_unit": "each",
        "forecast_unit": "each",
        "reason_code": "",
    }


def test_history_report_variance_by_item_is_uncapped():
    records = [
        {
            "production_record_id": 1,
            "week_number": 1,
            "day_of_week": "monday",
            "day_label": "Monday",
            "status_label": "Posted",
            "service_date_display": "Jun 1",
            "lines": [
                _history_line(item_id, f"Report Item {item_id}", item_id)
                for item_id in range(1, 11)
            ]
        }
    ]

    report = _build_history_report(
        records,
        {
            "reason_sort": "lines",
            "reason_dir": "desc",
            "variance_sort": "total",
            "variance_dir": "desc",
        },
    )

    assert len(report["variance_by_item"]) == 10


def test_history_report_variance_sort_can_order_shortage():
    records = [
        {
            "production_record_id": 1,
            "week_number": 1,
            "day_of_week": "monday",
            "day_label": "Monday",
            "status_label": "Posted",
            "service_date_display": "Jun 1",
            "lines": [
                _history_line(1, "Moderate Shortage", -3),
                _history_line(2, "Largest Shortage", -9),
                _history_line(3, "Small Shortage", -1),
            ]
        }
    ]

    report = _build_history_report(
        records,
        {
            "reason_sort": "lines",
            "reason_dir": "desc",
            "variance_sort": "shortage",
            "variance_dir": "desc",
        },
    )

    assert [row["recipe_name"] for row in report["variance_by_item"]] == [
        "Largest Shortage",
        "Moderate Shortage",
        "Small Shortage",
    ]
    assert report["variance_by_item"][0]["shortage_occurrences"][0]["quantity_display"] == "9"
