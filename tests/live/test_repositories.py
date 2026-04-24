from __future__ import annotations

from user_features.live.repositories import AIRepository, CrawlRepository, SpringRepository


def test_ai_repository_map_ingredient_code_returns_known_code():
    repo = AIRepository()
    assert repo.map_ingredient_code("난류") == "EGG"


def test_crawl_repository_load_menu_table_for_source_delegates(monkeypatch):
    repo = CrawlRepository()

    def fake_loader(*, cafeteria_name, source_url):
        assert cafeteria_name == "학생식당"
        assert source_url == "https://www.kumoh.ac.kr/ko/restaurant01.do"
        return {"ok": True}

    monkeypatch.setattr(
        "user_features.live.repositories.load_menu_table_for_source",
        fake_loader,
    )

    out = repo.load_menu_table_for_source(
        "학생식당",
        "https://www.kumoh.ac.kr/ko/restaurant01.do",
    )
    assert out == {"ok": True}


def test_spring_repository_post_json_delegates(monkeypatch):
    repo = SpringRepository()

    class DummyResponse:
        status_code = 200

    def fake_post_json(*, url, payload, token, api_key):
        assert url == "https://spring.example.com/endpoint"
        assert payload == {"hello": "world"}
        assert token == "token"
        assert api_key == "api-key"
        return DummyResponse()

    monkeypatch.setattr(
        "user_features.live.repositories.post_json",
        fake_post_json,
    )

    out = repo.post_json(
        url="https://spring.example.com/endpoint",
        payload={"hello": "world"},
        token="token",
        api_key="api-key",
    )
    assert out.status_code == 200
