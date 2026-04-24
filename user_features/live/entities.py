"""Live 서비스 도메인 엔티티."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MenuCrawlQuery:
    """식단 조회 도메인 질의 객체."""

    cafeteria_name: str
    source_url: str


@dataclass(frozen=True)
class SpringForwardPayload:
    """Spring 전달용 래퍼 엔티티."""

    url: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class FoodTextQuery:
    """텍스트 기반 음식 분석 질의."""

    food_name: str


@dataclass(frozen=True)
class FoodImageQuery:
    """이미지 기반 음식 분석 질의."""

    image_bytes: bytes
    mime_type: str
