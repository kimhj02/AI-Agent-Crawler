"""Live 라우터에서 사용하는 서비스 클래스."""

from __future__ import annotations

from typing import Any

import requests
from user_features.live.entities import FoodImageQuery, FoodTextQuery, MenuCrawlQuery, SpringForwardPayload
from user_features.live.repositories import AIRepository, CrawlRepository, SpringRepository
from user_features.live.runtime import RuntimeContext


class LiveService:
    """라우터에서 호출할 비즈니스 로직 진입점."""

    def __init__(self, ctx: RuntimeContext):
        self.cfg = ctx.config
        self.client = ctx.client
        self.crawl_repo = CrawlRepository()
        self.ai_repo = AIRepository()
        self.spring_repo = SpringRepository()

    def run_weekly_crawl_once(self) -> dict[str, Any]:
        return self.crawl_repo.run_weekly_crawl_once(self.cfg, self.client)

    def load_menu_table_for_source(self, cafeteria_name: str, source_url: str):
        query = MenuCrawlQuery(cafeteria_name=cafeteria_name, source_url=source_url)
        return self.crawl_repo.load_menu_table_for_source(query.cafeteria_name, query.source_url)

    def build_daily_meals(self, *, cafeteria_name: str, table: Any, start, end) -> list[dict[str, Any]]:
        return self.crawl_repo.build_daily_meals(
            cafeteria_name=cafeteria_name,
            table=table,
            start=start,
            end=end,
        )

    def analyze_food_text(self, food_name: str) -> dict[str, Any]:
        query = FoodTextQuery(food_name=food_name)
        return self.ai_repo.analyze_food_text(self.client, self.cfg.gemini_model, query.food_name)

    def identify_food_from_image(self, image_bytes: bytes, mime_type: str) -> dict[str, Any]:
        query = FoodImageQuery(image_bytes=image_bytes, mime_type=mime_type)
        return self.ai_repo.identify_food_from_image(
            self.client,
            self.cfg.gemini_model,
            query.image_bytes,
            query.mime_type,
        )

    def translate_text(self, source_lang: str, target_lang: str, text: str) -> str:
        return self.ai_repo.translate_text(
            self.client,
            self.cfg.gemini_model,
            source_lang,
            target_lang,
            text,
        )

    def map_ingredient_code(self, token: str) -> str | None:
        return self.ai_repo.map_ingredient_code(token)

    def forward_to_spring(
        self,
        *,
        url: str,
        payload: dict[str, Any],
    ) -> requests.Response:
        forward = SpringForwardPayload(url=url, payload=payload)
        return self.spring_repo.post_json(
            url=forward.url,
            payload=forward.payload,
            token=self.cfg.spring_api_token,
            api_key=self.cfg.spring_api_key,
        )

    @property
    def weekly_model(self) -> str:
        return self.cfg.weekly_menu_model

    @property
    def client_configured(self) -> bool:
        return self.client is not None
