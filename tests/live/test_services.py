from __future__ import annotations

from datetime import date

from user_features.live.runtime import RuntimeContext, ServiceConfig
from user_features.live.services import LiveService


def _build_ctx() -> RuntimeContext:
    cfg = ServiceConfig(
        spring_menus_url="https://spring.example.com/menus",
        spring_image_analysis_url="https://spring.example.com/image-analysis",
        spring_image_identify_url="https://spring.example.com/image-identify",
        spring_text_analysis_url="https://spring.example.com/text-analysis",
        spring_api_token="token-123",
        spring_api_key="key-123",
        gemini_model="gemini-2.5-flash-lite",
        weekly_menu_model="gemini-2.5-flash-lite",
        i18n_locale="en",
        weekly_batch_size=4,
        weekly_sleep_seconds=2.0,
        enable_direct_image_analysis=True,
        timezone_name="Asia/Seoul",
        crawl_weekday=0,
        crawl_hour=6,
        crawl_minute=0,
    )
    return RuntimeContext(config=cfg, client=None)


def test_analyze_food_text_delegates_to_ai_repository():
    svc = LiveService(_build_ctx())

    class StubAIRepo:
        def analyze_food_text(self, client, model_name, food_name):
            assert client is None
            assert model_name == "gemini-2.5-flash-lite"
            assert food_name == "비빔밥"
            return {"foodNameKo": "비빔밥"}

    svc.ai_repo = StubAIRepo()
    out = svc.analyze_food_text("비빔밥")
    assert out["foodNameKo"] == "비빔밥"


def test_build_daily_meals_delegates_to_crawl_repository():
    svc = LiveService(_build_ctx())

    class StubCrawlRepo:
        def build_daily_meals(self, *, cafeteria_name, table, start, end):
            assert cafeteria_name == "학생식당"
            assert table == {"k": "v"}
            assert start == date(2026, 3, 23)
            assert end == date(2026, 3, 27)
            return [{"mealDate": "2026-03-23", "mealType": "LUNCH", "menus": []}]

    svc.crawl_repo = StubCrawlRepo()
    out = svc.build_daily_meals(
        cafeteria_name="학생식당",
        table={"k": "v"},
        start=date(2026, 3, 23),
        end=date(2026, 3, 27),
    )
    assert out[0]["mealType"] == "LUNCH"


def test_forward_to_spring_uses_token_and_api_key():
    svc = LiveService(_build_ctx())

    class StubSpringRepo:
        def post_json(self, *, url, payload, token, api_key):
            assert url == "https://spring.example.com/ingest"
            assert payload == {"x": 1}
            assert token == "token-123"
            assert api_key == "key-123"
            return {"ok": True}

    svc.spring_repo = StubSpringRepo()
    res = svc.forward_to_spring(url="https://spring.example.com/ingest", payload={"x": 1})
    assert res["ok"] is True
