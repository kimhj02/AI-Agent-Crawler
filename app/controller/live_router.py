"""FastAPI 라우터 정의 (legacy + /api/v1)."""

from __future__ import annotations

import asyncio
import hmac
import logging
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

import requests
from fastapi import APIRouter, Body, File, Form, HTTPException, Request, Security, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.runtime import ALLOWED_MIME_TYPES, API_V1_PREFIX, MAX_IMAGE_SIZE, RuntimeContext
from app.dto.api_models import (
    ApiErrorResponse,
    ApiSuccessResponse,
    FoodImageAnalyzeDataResponse,
    FreeTranslationDataResponse,
    FreeTranslationRequest,
    LegacyCrawlForwardResponse,
    LegacyForwardResponse,
    LegacyHealthResponse,
    MenuBoardAnalyzeDataResponse,
    PythonMealCrawlDataResponse,
    PythonMealCrawlRequest,
    PythonMenuAnalysisDataResponse,
    PythonMenuAnalysisRequest,
    PythonMenuTranslationDataResponse,
    PythonMenuTranslationRequest,
)
from app.dto.openapi_examples import (
    AI_KEY_MISSING_EXAMPLE,
    BAD_REQUEST_COM001_EXAMPLE,
    FOOD_IMAGE_ANALYZE_RESPONSE_EXAMPLE,
    FREE_TRANSLATION_REQUEST_OPENAPI_EXAMPLES,
    FREE_TRANSLATION_SUCCESS_EXAMPLE,
    MEAL_CRAWL_ERROR_UPSTREAM_EXAMPLE,
    MEAL_CRAWL_REQUEST_OPENAPI_EXAMPLES,
    MEAL_CRAWL_SUCCESS_EXAMPLE,
    MENU_ANALYZE_REQUEST_OPENAPI_EXAMPLES,
    MENU_ANALYZE_SUCCESS_EXAMPLE,
    MENU_BOARD_ANALYZE_RESPONSE_EXAMPLE,
    MENU_TRANSLATE_REQUEST_OPENAPI_EXAMPLES,
    MENU_TRANSLATE_SUCCESS_EXAMPLE,
    VALIDATION_ERROR_EXAMPLE,
)
from app.service.live_service import LiveService
from app.util.service_ops import (
    CrawlSourceUpstreamError,
    sanitize_url_for_log,
    v1_error,
    v1_success,
    validate_accept_language,
)
from app.domain.image.agent import analyze_food_image_bytes

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


def _validate_image_upload_or_raise(image: UploadFile, image_bytes: bytes, mime_type: str) -> None:
    if not image_bytes:
        raise HTTPException(status_code=400, detail="이미지 파일이 비어 있습니다.")
    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail="이미지 파일이 너무 큽니다 (최대 10MB).")
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 이미지 형식: {mime_type}")


def _validate_image_upload_v1(image_bytes: bytes, mime_type: str) -> tuple[bool, Any]:
    if not image_bytes:
        return False, _v1_bad_request("이미지 파일이 비어 있습니다.")
    if len(image_bytes) > MAX_IMAGE_SIZE:
        return False, _v1_bad_request("이미지 파일이 너무 큽니다 (최대 10MB).")
    if mime_type not in ALLOWED_MIME_TYPES:
        return False, _v1_bad_request(f"지원하지 않는 이미지 형식: {mime_type}")
    return True, None


def _v1_bad_request(msg: str):
    return v1_error("COM_001", msg, status_code=400)


def _safe_float(value: Any, default: float = 0.5) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def create_legacy_router(ctx: RuntimeContext) -> APIRouter:
    service = LiveService(ctx)
    cfg = service.cfg
    client = service.client
    router = APIRouter(tags=["legacy"])

    @router.get("/health", summary="서비스 상태 확인", response_model=LegacyHealthResponse)
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "weeklyCrawlConfigured": cfg.spring_menus_url is not None,
            "imageAnalysisConfigured": cfg.spring_image_analysis_url is not None,
            "imageIdentifyConfigured": cfg.spring_image_identify_url is not None,
            "textAnalysisConfigured": cfg.spring_text_analysis_url is not None,
            "directImageAnalysisEnabled": cfg.enable_direct_image_analysis,
            "timezone": cfg.timezone_name,
        }

    @router.post(
        "/crawl-and-forward",
        summary="주간 식단 크롤링 후 Spring 전달",
        description="Python 서버가 식단을 수집/가공한 뒤 Spring Boot 수집 API로 전달합니다.",
        response_model=LegacyCrawlForwardResponse,
    )
    def crawl_and_forward(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> dict[str, Any]:
        if cfg.spring_api_token and (
            credentials is None
            or not hmac.compare_digest(credentials.credentials or "", cfg.spring_api_token)
        ):
            raise HTTPException(status_code=401, detail="Unauthorized")
        try:
            return service.run_weekly_crawl_once()
        except Exception:
            logger.exception("crawl-and-forward failed")
            raise HTTPException(status_code=500, detail="Internal Server Error")

    @router.post(
        "/analyze-image-and-forward",
        summary="음식 이미지 분석 후 Spring 전달",
        description="업로드한 음식 이미지에서 재료/알레르기 정보를 분석하고 결과를 Spring Boot로 전달합니다.",
        response_model=LegacyForwardResponse,
    )
    async def analyze_image_and_forward(
        image: UploadFile = File(...),
        user_id: Optional[str] = Form(default=None),
        request_id: Optional[str] = Form(default=None),
    ) -> dict[str, Any]:
        if not cfg.enable_direct_image_analysis:
            raise HTTPException(status_code=403, detail="Direct image analysis is disabled.")
        if client is None:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not set")
        if not cfg.spring_image_analysis_url:
            raise HTTPException(status_code=500, detail="SPRING_IMAGE_ANALYSIS_URL is not set")
        image_bytes = await image.read()
        mime_type = image.content_type or "image/jpeg"
        _validate_image_upload_or_raise(image, image_bytes, mime_type)
        analysis = await asyncio.to_thread(analyze_food_image_bytes, client, cfg.gemini_model, image_bytes, mime_type)
        payload = {"requestId": request_id, "userId": user_id, "capturedAt": datetime.now(ZoneInfo(cfg.timezone_name)).isoformat(), "analysis": analysis}
        res = await asyncio.to_thread(service.forward_to_spring, url=cfg.spring_image_analysis_url, payload=payload)
        if not res.ok:
            raise HTTPException(status_code=502, detail=f"Spring 응답 오류 HTTP {res.status_code}: {(res.text or '')[:500]}")
        return {"status": "ok", "forwardStatus": res.status_code, "analysis": analysis}

    @router.post(
        "/analyze-food-text-and-forward",
        summary="음식명 텍스트 분석 후 Spring 전달",
        description="음식 이름 텍스트를 분석해 재료/알레르기 가능 항목을 생성하고 Spring Boot로 전달합니다.",
        response_model=LegacyForwardResponse,
    )
    async def analyze_food_text_and_forward(food_name: str = Body(..., embed=True)) -> dict[str, Any]:
        if not cfg.spring_text_analysis_url:
            raise HTTPException(status_code=500, detail="SPRING_TEXT_ANALYSIS_URL is not set")
        analysis = await asyncio.to_thread(service.analyze_food_text, food_name.strip())
        payload = {"foodNameInput": food_name.strip(), "capturedAt": datetime.now(ZoneInfo(cfg.timezone_name)).isoformat(), "analysis": analysis}
        res = await asyncio.to_thread(service.forward_to_spring, url=cfg.spring_text_analysis_url, payload=payload)
        if not res.ok:
            raise HTTPException(status_code=502, detail=f"Spring 응답 오류 HTTP {res.status_code}")
        return {"status": "ok", "forwardStatus": res.status_code, "analysis": analysis}

    @router.post(
        "/identify-image-and-forward",
        summary="이미지 음식명 식별 후 Spring 전달",
        description="이미지에서 음식명을 식별하고 식별 결과를 Spring Boot로 전달합니다.",
        response_model=LegacyForwardResponse,
    )
    async def identify_image_and_forward(
        image: UploadFile = File(...),
        request_id: Optional[str] = Form(default=None),
    ) -> dict[str, Any]:
        if not cfg.spring_image_identify_url:
            raise HTTPException(status_code=500, detail="SPRING_IMAGE_IDENTIFY_URL is not set")
        image_bytes = await image.read()
        mime_type = image.content_type or "image/jpeg"
        _validate_image_upload_or_raise(image, image_bytes, mime_type)
        identified = await asyncio.to_thread(service.identify_food_from_image, image_bytes, mime_type)
        payload = {"requestId": request_id, "capturedAt": datetime.now(ZoneInfo(cfg.timezone_name)).isoformat(), "identified": identified}
        res = await asyncio.to_thread(service.forward_to_spring, url=cfg.spring_image_identify_url, payload=payload)
        if not res.ok:
            raise HTTPException(status_code=502, detail=f"Spring 응답 오류 HTTP {res.status_code}")
        return {"status": "ok", "forwardStatus": res.status_code, "identified": identified}

    return router


def create_v1_router(ctx: RuntimeContext) -> APIRouter:
    service = LiveService(ctx)
    cfg = service.cfg
    client = service.client
    router = APIRouter(prefix=API_V1_PREFIX)

    @router.post(
        "/python/meals/crawl",
        tags=["v1-meals"],
        summary="식단 기간 조회/크롤링",
        description="학교/식당/기간 조건으로 식단을 조회하고 메뉴 목록을 표준 DTO로 반환합니다.",
        operation_id="crawlMealsV1",
        response_model=ApiSuccessResponse[PythonMealCrawlDataResponse],
        responses={
            200: {
                "description": "조회 성공",
                "content": {
                    "application/json": {
                        "examples": {
                            "식단포함": {
                                "summary": "meals에 일자별 메뉴 포함",
                                "value": MEAL_CRAWL_SUCCESS_EXAMPLE,
                            }
                        }
                    }
                },
            },
            400: {
                "model": ApiErrorResponse,
                "content": {
                    "application/json": {
                        "examples": {
                            "검증실패": {"summary": "스키마/헤더 검증 오류", "value": VALIDATION_ERROR_EXAMPLE},
                            "조건불가": {
                                "summary": "식당/URL 조건 오류",
                                "value": {
                                    "success": False,
                                    "code": "PYM_400",
                                    "msg": "요청 식단 조회 조건이 유효하지 않거나 데이터가 없습니다.",
                                },
                            },
                        }
                    }
                },
            },
            502: {
                "model": ApiErrorResponse,
                "content": {
                    "application/json": {
                        "examples": {
                            "업스트림실패": {"summary": "외부 크롤 소스 실패", "value": MEAL_CRAWL_ERROR_UPSTREAM_EXAMPLE},
                        }
                    }
                },
            },
            500: {"model": ApiErrorResponse},
        },
    )
    def crawl_meals_v1(
        request: Request,
        payload: PythonMealCrawlRequest = Body(..., openapi_examples=MEAL_CRAWL_REQUEST_OPENAPI_EXAMPLES),
    ):
        try:
            validate_accept_language(request.headers.get("Accept-Language"))
        except ValueError as e:
            return _v1_bad_request(str(e))
        if payload.startDate > payload.endDate:
            return _v1_bad_request("startDate는 endDate보다 이후일 수 없습니다.")
        try:
            table = service.load_menu_table_for_source(payload.cafeteriaName, payload.sourceUrl)
        except RuntimeError as e:
            logger.warning("crawl bad request cafeteria=%s reason=%s", payload.cafeteriaName, e)
            return v1_error("PYM_400", "요청 식단 조회 조건이 유효하지 않거나 데이터가 없습니다.", status_code=400)
        except (CrawlSourceUpstreamError, requests.exceptions.RequestException, OSError) as e:
            logger.warning("upstream crawl source unavailable source=%s cafeteriaName=%s: %s", sanitize_url_for_log(payload.sourceUrl), payload.cafeteriaName, e)
            return v1_error("PYM_502", "외부 크롤링 소스 조회에 실패했습니다. 잠시 후 다시 시도해주세요.", status_code=502)
        meals = service.build_daily_meals(cafeteria_name=payload.cafeteriaName, table=table, start=payload.startDate, end=payload.endDate)
        return v1_success({"schoolName": payload.schoolName, "cafeteriaName": payload.cafeteriaName, "sourceUrl": payload.sourceUrl, "startDate": payload.startDate.isoformat(), "endDate": payload.endDate.isoformat(), "meals": meals})

    @router.post(
        "/python/menus/analyze",
        tags=["v1-ai"],
        summary="메뉴 텍스트 AI 분석",
        description="메뉴명 리스트를 받아 재료 코드/신뢰도 추정 결과를 반환합니다.",
        operation_id="analyzeMenusV1",
        response_model=ApiSuccessResponse[PythonMenuAnalysisDataResponse],
        responses={
            200: {
                "description": "분석 성공",
                "content": {
                    "application/json": {
                        "examples": {
                            "재료추정": {"summary": "ingredients 포함", "value": MENU_ANALYZE_SUCCESS_EXAMPLE},
                        }
                    }
                },
            },
            400: {
                "model": ApiErrorResponse,
                "content": {
                    "application/json": {
                        "examples": {
                            "검증실패": {"value": VALIDATION_ERROR_EXAMPLE},
                        }
                    }
                },
            },
            500: {
                "model": ApiErrorResponse,
                "content": {
                    "application/json": {
                        "examples": {
                            "키미설정": {"summary": "GEMINI 미설정", "value": AI_KEY_MISSING_EXAMPLE},
                        }
                    }
                },
            },
        },
    )
    async def analyze_menus_v1(
        request: Request,
        payload: PythonMenuAnalysisRequest = Body(..., openapi_examples=MENU_ANALYZE_REQUEST_OPENAPI_EXAMPLES),
    ):
        try:
            validate_accept_language(request.headers.get("Accept-Language"))
        except ValueError as e:
            return _v1_bad_request(str(e))
        if client is None:
            return v1_error("AI_001", "GEMINI_API_KEY is not set", status_code=500)
        results = await service.analyze_menus(payload.menus, max_concurrency=cfg.ai_max_concurrent_tasks)
        return v1_success({"results": results})

    @router.post(
        "/python/menus/translate",
        tags=["v1-translation"],
        summary="메뉴 다국어 번역",
        description="메뉴명 리스트를 요청 언어 목록으로 번역해 반환합니다.",
        operation_id="translateMenusV1",
        response_model=ApiSuccessResponse[PythonMenuTranslationDataResponse],
        responses={
            200: {
                "description": "번역 성공",
                "content": {
                    "application/json": {
                        "examples": {
                            "다국어": {"summary": "translations 배열", "value": MENU_TRANSLATE_SUCCESS_EXAMPLE},
                        }
                    }
                },
            },
            400: {
                "model": ApiErrorResponse,
                "content": {
                    "application/json": {
                        "examples": {
                            "검증실패": {"value": VALIDATION_ERROR_EXAMPLE},
                        }
                    }
                },
            },
            500: {
                "model": ApiErrorResponse,
                "content": {
                    "application/json": {
                        "examples": {
                            "키미설정": {"value": AI_KEY_MISSING_EXAMPLE},
                        }
                    }
                },
            },
        },
    )
    async def translate_menus_v1(
        request: Request,
        payload: PythonMenuTranslationRequest = Body(..., openapi_examples=MENU_TRANSLATE_REQUEST_OPENAPI_EXAMPLES),
    ):
        try:
            validate_accept_language(request.headers.get("Accept-Language"))
        except ValueError as e:
            return _v1_bad_request(str(e))
        if client is None:
            return v1_error("AI_001", "GEMINI_API_KEY is not set", status_code=500)
        results = await service.translate_menus(
            payload.menus,
            target_languages=payload.targetLanguages,
            max_concurrency=cfg.ai_max_concurrent_tasks,
        )
        return v1_success({"results": results})

    @router.post(
        "/translations",
        tags=["v1-translation"],
        summary="자유 문장 번역",
        description="sourceLang/targetLang 기준으로 일반 텍스트를 번역합니다.",
        operation_id="freeTranslationV1",
        response_model=ApiSuccessResponse[FreeTranslationDataResponse],
        responses={
            200: {
                "description": "번역 성공",
                "content": {
                    "application/json": {
                        "examples": {
                            "문장번역": {"value": FREE_TRANSLATION_SUCCESS_EXAMPLE},
                        }
                    }
                },
            },
            400: {
                "model": ApiErrorResponse,
                "content": {
                    "application/json": {
                        "examples": {
                            "검증실패": {"value": VALIDATION_ERROR_EXAMPLE},
                        }
                    }
                },
            },
            500: {"model": ApiErrorResponse},
        },
    )
    async def free_translation_v1(
        request: Request,
        payload: FreeTranslationRequest = Body(..., openapi_examples=FREE_TRANSLATION_REQUEST_OPENAPI_EXAMPLES),
    ):
        try:
            validate_accept_language(request.headers.get("Accept-Language"))
        except ValueError as e:
            return _v1_bad_request(str(e))
        translated = await asyncio.to_thread(service.translate_text, payload.sourceLang, payload.targetLang, payload.text)
        return v1_success({"sourceLang": payload.sourceLang, "targetLang": payload.targetLang, "text": payload.text, "translatedText": translated})

    @router.post(
        "/ai/menu-board/analyze",
        tags=["v1-ai"],
        summary="메뉴판 이미지 인식",
        description="메뉴판 사진에서 음식명을 인식해 후보 메뉴를 반환합니다. `multipart/form-data`로 `image`(필수), `requestId`(선택)를 전송합니다.",
        operation_id="analyzeMenuBoardV1",
        response_model=ApiSuccessResponse[MenuBoardAnalyzeDataResponse],
        responses={
            200: {
                "description": "인식 성공",
                "content": {
                    "application/json": {
                        "examples": {
                            "메뉴후보": {"value": MENU_BOARD_ANALYZE_RESPONSE_EXAMPLE},
                        }
                    }
                },
            },
            400: {
                "model": ApiErrorResponse,
                "content": {
                    "application/json": {
                        "examples": {
                            "이미지검증": {"value": BAD_REQUEST_COM001_EXAMPLE},
                            "검증실패": {"value": VALIDATION_ERROR_EXAMPLE},
                        }
                    }
                },
            },
            500: {
                "model": ApiErrorResponse,
                "content": {
                    "application/json": {
                        "examples": {
                            "키미설정": {"value": AI_KEY_MISSING_EXAMPLE},
                        }
                    }
                },
            },
        },
    )
    async def analyze_menu_board_v1(request: Request, image: UploadFile = File(...), requestId: Optional[str] = Form(default=None)):
        try:
            validate_accept_language(request.headers.get("Accept-Language"))
        except ValueError as e:
            return _v1_bad_request(str(e))
        if client is None:
            return v1_error("AI_001", "GEMINI_API_KEY is not set", status_code=500)
        image_bytes = await image.read()
        mime_type = image.content_type or "image/jpeg"
        valid, err = _validate_image_upload_v1(image_bytes, mime_type)
        if not valid:
            return err
        identified = await asyncio.to_thread(service.identify_food_from_image, image_bytes, mime_type)
        return v1_success({"requestId": requestId, "recognizedMenus": [{"menuName": identified.get("foodNameKo"), "confidence": identified.get("confidence")}]})

    @router.post(
        "/ai/food-images/analyze",
        tags=["v1-ai"],
        summary="음식 이미지 재료/알레르기 분석",
        description="음식 사진을 분석해 재료 코드와 알레르기 가능 항목을 반환합니다. `multipart/form-data`로 `image`(필수), `requestId`(선택)를 전송합니다.",
        operation_id="analyzeFoodImageV1",
        response_model=ApiSuccessResponse[FoodImageAnalyzeDataResponse],
        responses={
            200: {
                "description": "분석 성공",
                "content": {
                    "application/json": {
                        "examples": {
                            "재료추정": {"value": FOOD_IMAGE_ANALYZE_RESPONSE_EXAMPLE},
                        }
                    }
                },
            },
            400: {
                "model": ApiErrorResponse,
                "content": {
                    "application/json": {
                        "examples": {
                            "이미지검증": {"value": BAD_REQUEST_COM001_EXAMPLE},
                            "검증실패": {"value": VALIDATION_ERROR_EXAMPLE},
                        }
                    }
                },
            },
            500: {
                "model": ApiErrorResponse,
                "content": {
                    "application/json": {
                        "examples": {
                            "키미설정": {"value": AI_KEY_MISSING_EXAMPLE},
                        }
                    }
                },
            },
        },
    )
    async def analyze_food_image_v1(request: Request, image: UploadFile = File(...), requestId: Optional[str] = Form(default=None)):
        try:
            validate_accept_language(request.headers.get("Accept-Language"))
        except ValueError as e:
            return _v1_bad_request(str(e))
        if client is None:
            return v1_error("AI_001", "GEMINI_API_KEY is not set", status_code=500)
        image_bytes = await image.read()
        mime_type = image.content_type or "image/jpeg"
        valid, err = _validate_image_upload_v1(image_bytes, mime_type)
        if not valid:
            return err
        analysis = await asyncio.to_thread(analyze_food_image_bytes, client, cfg.gemini_model, image_bytes, mime_type)
        ingredients = []
        for item in analysis.get("추정_식재료") or []:
            if not isinstance(item, dict):
                continue
            code = service.map_ingredient_code(str(item.get("재료", "")).strip())
            if not code:
                continue
            ingredients.append({"ingredientCode": code, "confidence": _safe_float(item.get("신뢰도", 0.5), default=0.5)})
        return v1_success({"requestId": requestId, "foodName": analysis.get("음식명"), "ingredients": ingredients, "notes": analysis.get("주의사항")})

    return router
