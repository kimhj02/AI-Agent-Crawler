"""Spring `PythonMealClientAdapter`가 기대하는 비래핑 JSON 계약 (`MealCrawlProperties` 기본 경로).

`RestClient`는 응답 본문을 `PythonMealCrawlResponse` 등 단일 객체로 역직렬화하므로
`success`/`data` 래핑 없이 루트에 DTO 필드를 둡니다.
"""

from __future__ import annotations

import logging
import requests
from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from app.common.service_ops import CrawlSourceUpstreamError, sanitize_url_for_log, validate_accept_language
from app.config.runtime import API_V1_PREFIX, RuntimeContext
from app.schemas.api_models import PythonMealCrawlRequest, PythonMenuAnalysisRequest, PythonMenuTranslationRequest
from app.services.live_service import LiveService

logger = logging.getLogger(__name__)


def create_spring_native_router(ctx: RuntimeContext) -> APIRouter:
    service = LiveService(ctx)
    cfg = service.cfg
    client = service.client
    router = APIRouter(prefix=API_V1_PREFIX, tags=["spring-meal-client"])

    @router.post(
        "/crawl/meals",
        summary="Spring 연동 식단 크롤 (비래핑)",
        description="`mealguide.mealcrawl.crawl-path` 기본값(`/api/v1/crawl/meals`)과 동일합니다.",
        response_model=None,
    )
    def crawl_meals_spring_native(request: Request, payload: PythonMealCrawlRequest = Body(...)):
        try:
            validate_accept_language(request.headers.get("Accept-Language"))
        except ValueError as e:
            return _spring_bad_request(str(e))
        if payload.startDate > payload.endDate:
            return _spring_bad_request("startDate는 endDate보다 이후일 수 없습니다.")
        try:
            table = service.load_menu_table_for_source(payload.cafeteriaName, payload.sourceUrl)
        except RuntimeError as e:
            logger.warning("spring-native crawl bad request cafeteria=%s reason=%s", payload.cafeteriaName, e)
            return _spring_bad_request("요청 식단 조회 조건이 유효하지 않거나 데이터가 없습니다.", status_code=400)
        except (CrawlSourceUpstreamError, requests.exceptions.RequestException, OSError) as e:
            logger.warning(
                "spring-native upstream unavailable source=%s cafeteriaName=%s: %s",
                sanitize_url_for_log(payload.sourceUrl),
                payload.cafeteriaName,
                e,
            )
            return _spring_bad_request(
                "외부 크롤링 소스 조회에 실패했습니다. 잠시 후 다시 시도해주세요.",
                status_code=502,
            )
        meals = service.build_daily_meals(
            cafeteria_name=payload.cafeteriaName,
            table=table,
            start=payload.startDate,
            end=payload.endDate,
        )
        return {
            "schoolName": payload.schoolName,
            "cafeteriaName": payload.cafeteriaName,
            "sourceUrl": payload.sourceUrl,
            "startDate": payload.startDate.isoformat(),
            "endDate": payload.endDate.isoformat(),
            "meals": meals,
        }

    @router.post(
        "/menus/analyze",
        summary="Spring 연동 메뉴 분석 (비래핑)",
        description="`mealguide.mealcrawl.analysis-path` 기본값(`/api/v1/menus/analyze`)과 동일합니다.",
        response_model=None,
    )
    async def analyze_menus_spring_native(request: Request, payload: PythonMenuAnalysisRequest = Body(...)):
        try:
            validate_accept_language(request.headers.get("Accept-Language"))
        except ValueError as e:
            return _spring_bad_request(str(e))
        if client is None:
            return _spring_bad_request("GEMINI_API_KEY is not set", status_code=500)
        results = await service.analyze_menus(payload.menus, max_concurrency=cfg.ai_max_concurrent_tasks)
        return {"results": results}

    @router.post(
        "/menus/translate",
        summary="Spring 연동 메뉴 번역 (비래핑)",
        description="`mealguide.mealcrawl.translation-path` 기본값(`/api/v1/menus/translate`)과 동일합니다.",
        response_model=None,
    )
    async def translate_menus_spring_native(request: Request, payload: PythonMenuTranslationRequest = Body(...)):
        try:
            validate_accept_language(request.headers.get("Accept-Language"))
        except ValueError as e:
            return _spring_bad_request(str(e))
        if client is None:
            return _spring_bad_request("GEMINI_API_KEY is not set", status_code=500)
        results = await service.translate_menus(
            payload.menus,
            target_languages=payload.targetLanguages,
            max_concurrency=cfg.ai_max_concurrent_tasks,
        )
        return {"results": results}

    return router


def _spring_bad_request(msg: str, *, status_code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"message": msg})
