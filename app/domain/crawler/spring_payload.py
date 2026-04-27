"""크롤링한 급식표를 Spring Boot 등 HTTP API용 JSON으로 직렬화합니다."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd


def _cell_str(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def build_menu_ingest_payload(
    menus: dict[str, pd.DataFrame],
    *,
    source: str = "https://www.kumoh.ac.kr",
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    when = captured_at or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = datetime(
            when.year,
            when.month,
            when.day,
            when.hour,
            when.minute,
            when.second,
            when.microsecond,
            tzinfo=timezone.utc,
        )
    else:
        when = when.astimezone(timezone.utc)

    restaurants: list[dict[str, Any]] = []
    for place_name, df in menus.items():
        columns = [str(c).strip() for c in df.columns]
        rows: list[list[str]] = []
        for _, row in df.iterrows():
            rows.append([_cell_str(row[c]) for c in df.columns])
        restaurants.append({"name": place_name, "columns": columns, "rows": rows})

    return {
        "source": source,
        "capturedAt": when.isoformat(),
        "restaurants": restaurants,
    }


def build_menu_ingest_swagger_payload(
    menus: dict[str, pd.DataFrame],
    *,
    source: str = "https://www.kumoh.ac.kr",
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    base = build_menu_ingest_payload(
        menus,
        source=source,
        captured_at=captured_at,
    )
    return {
        "success": True,
        "data": base,
    }
