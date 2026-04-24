"""Live 서비스에서 사용하는 Repository 계층."""

from __future__ import annotations

from typing import Any

import requests
from google import genai

from user_features.live.service_ops import (
    analyze_food_text,
    build_daily_meals,
    identify_food_from_image,
    load_menu_table_for_source,
    map_ingredient_code,
    post_json,
    run_weekly_crawl_once,
    translate_text_with_gemini,
)


class CrawlRepository:
    """크롤링/메뉴 데이터 접근 Repository."""

    def load_menu_table_for_source(self, cafeteria_name: str, source_url: str):
        return load_menu_table_for_source(cafeteria_name=cafeteria_name, source_url=source_url)

    def build_daily_meals(self, *, cafeteria_name: str, table: Any, start, end) -> list[dict[str, Any]]:
        return build_daily_meals(cafeteria_name=cafeteria_name, table=table, start=start, end=end)

    def run_weekly_crawl_once(self, cfg, client: genai.Client | None) -> dict[str, Any]:
        return run_weekly_crawl_once(cfg, client)


class AIRepository:
    """Gemini 호출/재료 코드 매핑 Repository."""

    def analyze_food_text(self, client: genai.Client | None, model_name: str, food_name: str) -> dict[str, Any]:
        return analyze_food_text(client, model_name, food_name)

    def identify_food_from_image(
        self,
        client: genai.Client | None,
        model_name: str,
        image_bytes: bytes,
        mime_type: str,
    ) -> dict[str, Any]:
        return identify_food_from_image(client, model_name, image_bytes, mime_type)

    def translate_text(
        self,
        client: genai.Client | None,
        model_name: str,
        source_lang: str,
        target_lang: str,
        text: str,
    ) -> str:
        return translate_text_with_gemini(client, model_name, source_lang, target_lang, text)

    def map_ingredient_code(self, token: str) -> str | None:
        return map_ingredient_code(token)


class SpringRepository:
    """Spring API 연동 Repository."""

    def post_json(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        token: str | None,
        api_key: str | None,
    ) -> requests.Response:
        return post_json(url=url, payload=payload, token=token, api_key=api_key)
