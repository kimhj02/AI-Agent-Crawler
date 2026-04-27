"""크롤 원본 + (선택) 분석 CSV + 알레르기 필터 + (선택) 다국어 블록을 한 페이로드로 묶습니다."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from app.domain.crawler.spring_payload import build_menu_ingest_swagger_payload
from user_features.allergy_filter import (
    avoid_menus_for_api_payload,
    filter_avoid_dataframe,
    normalize_user_allergen_tokens,
)


def build_extended_menu_payload(
    menus: dict[str, pd.DataFrame],
    *,
    source: str = "https://www.kumoh.ac.kr",
    captured_at: datetime | None = None,
    analysis_df: pd.DataFrame | None = None,
    user_allergens_raw: list[str] | None = None,
    today_only_avoid: bool = False,
    i18n_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Spring Boot 등에 넘기기 좋은 확장 페이로드.

    - 기본: Swagger 공통 래핑(success/data) 구조
    - data 내부에 source/capturedAt/restaurants + 확장 필드를 배치
    - userAllergensKo: 사용자가 고른 알레르기(canonical)
    - avoidMenus: 분석 CSV가 있고 알레르기가 지정된 경우에만
    - i18nSummary: 호출 측에서 Gemini 등으로 채운 블록을 그대로 첨부
    """
    wrapped = build_menu_ingest_swagger_payload(
        menus,
        source=source,
        captured_at=captured_at,
    )
    base = wrapped["data"]

    if user_allergens_raw:
        canon = normalize_user_allergen_tokens(user_allergens_raw)
        base["userAllergensKo"] = sorted(canon)

    if analysis_df is not None and user_allergens_raw:
        avoid_df = filter_avoid_dataframe(
            analysis_df,
            canon,
            today_only=today_only_avoid,
        )
        base["avoidMenus"] = avoid_menus_for_api_payload(avoid_df)
    elif user_allergens_raw and analysis_df is None:
        base.setdefault("avoidMenus", [])

    if i18n_summary is not None:
        base["i18nSummary"] = i18n_summary

    return wrapped
