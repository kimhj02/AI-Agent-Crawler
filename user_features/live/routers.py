"""FastAPI 라우터 정의 (legacy + /api/v1)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests
from fastapi import APIRouter, Body, File, Form, HTTPException, Request, Security, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from food_image.agent import analyze_food_image_bytes
from user_features.live.api_models import (
    FreeTranslationRequest,
    PythonMealCrawlRequest,
    PythonMenuAnalysisRequest,
    PythonMenuTranslationRequest,
)
from user_features.live.runtime import (
    ALLOWED_MIME_TYPES,
    API_V1_PREFIX,
    MAX_IMAGE_SIZE,
    RuntimeContext,
)
from user_features.live.service_ops import (
    CrawlSourceUpstreamError,
    analyze_food_text,
    build_daily_meals,
    identify_food_from_image,
    load_menu_table_for_source,
    map_ingredient_code,
    post_json,
    run_weekly_crawl_once,
    sanitize_url_for_log,
    translate_text_with_gemini,
    v1_error,
    v1_success,
    validate_accept_language,
)

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)
MAX_CONCURRENT_AI_TASKS = 4


def _validate_image_upload_or_raise(image: UploadFile, image_bytes: bytes, mime_type: str) -> None:
    if not image_bytes:
        raise HTTPException(status_code=400, detail="이미지 파일이 비어 있습니다.")
    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail="이미지 파일이 너무 큽니다 (최대 10MB).")
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 이미지 형식: {mime_type}")


def _validate_image_upload_v1(
    image_bytes: bytes,
    mime_type: str,
) -> tuple[bool, Any]:
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
    """기존 운영 호환용 엔드포인트 묶음."""
    cfg = ctx.config
    client = ctx.client
    router = APIRouter()

    @router.get("/health")
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

    @router.post("/crawl-and-forward")
    def crawl_and_forward(
        credentials: HTTPAuthorizationCredentials | None = Security(security),
    ) -> dict[str, Any]:
        if cfg.spring_api_token and (
            credentials is None or credentials.credentials != cfg.spring_api_token
        ):
            raise HTTPException(status_code=401, detail="Unauthorized")
        try:
            return run_weekly_crawl_once(cfg, client)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/analyze-image-and-forward")
    async def analyze_image_and_forward(
        image: UploadFile = File(...),
        user_id: str | None = Form(default=None),
        request_id: str | None = Form(default=None),
    ) -> dict[str, Any]:
        if not cfg.enable_direct_image_analysis:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Direct image analysis is disabled. "
                    "Set ENABLE_DIRECT_IMAGE_ANALYSIS=true to enable."
                ),
            )
        if client is None:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not set")
        if not cfg.spring_image_analysis_url:
            raise HTTPException(status_code=500, detail="SPRING_IMAGE_ANALYSIS_URL is not set")

        image_bytes = await image.read()
        mime_type = image.content_type or "image/jpeg"
        _validate_image_upload_or_raise(image, image_bytes, mime_type)

        try:
            analysis = await asyncio.to_thread(
                analyze_food_image_bytes,
                client,
                cfg.gemini_model,
                image_bytes,
                mime_type,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"이미지 분석 실패: {e}") from e

        payload = {
            "requestId": request_id,
            "userId": user_id,
            "capturedAt": datetime.now(ZoneInfo(cfg.timezone_name)).isoformat(),
            "analysis": analysis,
        }
        try:
            res = await asyncio.to_thread(
                post_json,
                url=cfg.spring_image_analysis_url,
                payload=payload,
                token=cfg.spring_api_token,
                api_key=cfg.spring_api_key,
            )
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"Spring 전송 실패: {e}") from e

        if not res.ok:
            raise HTTPException(
                status_code=502,
                detail=f"Spring 응답 오류 HTTP {res.status_code}: {(res.text or '')[:500]}",
            )
        return {"status": "ok", "forwardStatus": res.status_code, "analysis": analysis}

    @router.post("/analyze-food-text-and-forward")
    async def analyze_food_text_and_forward(
        food_name: str = Body(..., embed=True, description="분석할 음식 이름"),
    ) -> dict[str, Any]:
        if not cfg.spring_text_analysis_url:
            raise HTTPException(status_code=500, detail="SPRING_TEXT_ANALYSIS_URL is not set")
        if not food_name.strip():
            raise HTTPException(status_code=400, detail="food_name is empty")

        try:
            analysis = await asyncio.to_thread(
                analyze_food_text,
                client,
                cfg.gemini_model,
                food_name.strip(),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"텍스트 음식 분석 실패: {e}") from e

        payload = {
            "foodNameInput": food_name.strip(),
            "capturedAt": datetime.now(ZoneInfo(cfg.timezone_name)).isoformat(),
            "analysis": analysis,
        }
        try:
            res = await asyncio.to_thread(
                post_json,
                url=cfg.spring_text_analysis_url,
                payload=payload,
                token=cfg.spring_api_token,
                api_key=cfg.spring_api_key,
            )
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"Spring 전송 실패: {e}") from e

        if not res.ok:
            raise HTTPException(status_code=502, detail=f"Spring 응답 오류 HTTP {res.status_code}")
        return {"status": "ok", "forwardStatus": res.status_code, "analysis": analysis}

    @router.post("/identify-image-and-forward")
    async def identify_image_and_forward(
        image: UploadFile = File(...),
        request_id: str | None = Form(default=None),
    ) -> dict[str, Any]:
        if not cfg.spring_image_identify_url:
            raise HTTPException(status_code=500, detail="SPRING_IMAGE_IDENTIFY_URL is not set")
        image_bytes = await image.read()
        mime_type = image.content_type or "image/jpeg"
        _validate_image_upload_or_raise(image, image_bytes, mime_type)

        try:
            identified = await asyncio.to_thread(
                identify_food_from_image,
                client,
                cfg.gemini_model,
                image_bytes,
                mime_type,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"이미지 음식 식별 실패: {e}") from e

        payload = {
            "requestId": request_id,
            "capturedAt": datetime.now(ZoneInfo(cfg.timezone_name)).isoformat(),
            "identified": identified,
        }
        try:
            res = await asyncio.to_thread(
                post_json,
                url=cfg.spring_image_identify_url,
                payload=payload,
                token=cfg.spring_api_token,
                api_key=cfg.spring_api_key,
            )
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"Spring 전송 실패: {e}") from e

        if not res.ok:
            raise HTTPException(status_code=502, detail=f"Spring 응답 오류 HTTP {res.status_code}")
        return {"status": "ok", "forwardStatus": res.status_code, "identified": identified}

    return router


def create_v1_router(ctx: RuntimeContext) -> APIRouter:
    """신규 `/api/v1` 스펙 엔드포인트 묶음."""
    cfg = ctx.config
    client = ctx.client
    router = APIRouter(prefix=API_V1_PREFIX)

    @router.post("/python/meals/crawl")
    def crawl_meals_v1(payload: PythonMealCrawlRequest, request: Request):
        try:
            validate_accept_language(request.headers.get("Accept-Language"))
        except ValueError as e:
            return _v1_bad_request(str(e))
        if payload.startDate > payload.endDate:
            return _v1_bad_request("startDate는 endDate보다 이후일 수 없습니다.")

        try:
            table = load_menu_table_for_source(
                cafeteria_name=payload.cafeteriaName,
                source_url=payload.sourceUrl,
            )
        except RuntimeError as e:
            return v1_error(
                "PYM_400",
                (
                    "요청 식단 조회 조건이 유효하지 않거나 데이터가 없습니다. "
                    f"(cafeteriaName={payload.cafeteriaName}, sourceUrl={payload.sourceUrl}, reason={e})"
                ),
                status_code=400,
            )
        except (CrawlSourceUpstreamError, requests.exceptions.RequestException, OSError) as e:
            logger.warning(
                "upstream crawl source unavailable source=%s cafeteriaName=%s: %s",
                sanitize_url_for_log(payload.sourceUrl),
                payload.cafeteriaName,
                e,
            )
            return v1_error(
                "PYM_502",
                (
                    "외부 크롤링 소스 조회에 실패했습니다. 잠시 후 다시 시도해주세요. "
                    f"(cafeteriaName={payload.cafeteriaName}, sourceUrl={payload.sourceUrl})"
                ),
                status_code=502,
            )
        except Exception as e:
            logger.exception(
                "unexpected error while loading menu table source=%s cafeteriaName=%s",
                sanitize_url_for_log(payload.sourceUrl),
                payload.cafeteriaName,
            )
            return v1_error(
                "PYM_500",
                (
                    "요청 식단 조회 중 예상하지 못한 오류가 발생했습니다. "
                    f"(cafeteriaName={payload.cafeteriaName}, sourceUrl={payload.sourceUrl}, reason={e})"
                ),
                status_code=500,
            )

        meals = build_daily_meals(
            cafeteria_name=payload.cafeteriaName,
            table=table,
            start=payload.startDate,
            end=payload.endDate,
        )
        return v1_success(
            {
                "schoolName": payload.schoolName,
                "cafeteriaName": payload.cafeteriaName,
                "sourceUrl": payload.sourceUrl,
                "startDate": payload.startDate.isoformat(),
                "endDate": payload.endDate.isoformat(),
                "meals": meals,
            }
        )

    @router.post("/python/menus/analyze")
    async def analyze_menus_v1(payload: PythonMenuAnalysisRequest, request: Request):
        try:
            validate_accept_language(request.headers.get("Accept-Language"))
        except ValueError as e:
            return _v1_bad_request(str(e))
        if client is None:
            return v1_error("AI_001", "GEMINI_API_KEY is not set", status_code=500)

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_AI_TASKS)

        async def _analyze_single_menu(target) -> dict[str, Any]:
            analyzed_at = datetime.now(ZoneInfo(cfg.timezone_name)).isoformat(timespec="seconds")
            try:
                async with semaphore:
                    analysis = await asyncio.to_thread(
                        analyze_food_text,
                        client,
                        cfg.gemini_model,
                        target.menuName,
                    )
                ingredient_codes: list[dict[str, Any]] = []
                dedup: set[str] = set()

                for idx, ingredient in enumerate(analysis.get("ingredientsKo") or []):
                    code = map_ingredient_code(str(ingredient).strip())
                    if not code or code in dedup:
                        continue
                    dedup.add(code)
                    ingredient_codes.append(
                        {
                            "ingredientCode": code,
                            "confidence": round(max(0.5, 0.95 - (idx * 0.07)), 2),
                        }
                    )

                for allergen in analysis.get("allergensKo") or []:
                    if not isinstance(allergen, dict):
                        continue
                    code = map_ingredient_code(str(allergen.get("name", "")).strip())
                    if not code or code in dedup:
                        continue
                    dedup.add(code)
                    ingredient_codes.append({"ingredientCode": code, "confidence": 0.8})

                return {
                    "menuId": target.menuId,
                    "menuName": target.menuName,
                    "status": "COMPLETED",
                    "reason": None,
                    "modelName": "gemini",
                    "modelVersion": cfg.gemini_model,
                    "analyzedAt": analyzed_at,
                    "ingredients": ingredient_codes,
                }
            except Exception as e:
                return {
                    "menuId": target.menuId,
                    "menuName": target.menuName,
                    "status": "FAILED",
                    "reason": str(e)[:300],
                    "modelName": "gemini",
                    "modelVersion": cfg.gemini_model,
                    "analyzedAt": analyzed_at,
                    "ingredients": [],
                }

        results = await asyncio.gather(*[_analyze_single_menu(target) for target in payload.menus])

        return v1_success({"results": results})

    @router.post("/python/menus/translate")
    async def translate_menus_v1(payload: PythonMenuTranslationRequest, request: Request):
        try:
            validate_accept_language(request.headers.get("Accept-Language"))
        except ValueError as e:
            return _v1_bad_request(str(e))
        if client is None:
            return v1_error("AI_001", "GEMINI_API_KEY is not set", status_code=500)

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_AI_TASKS)

        async def _translate_single_menu(menu) -> dict[str, Any]:
            translations: list[dict[str, str]] = []
            translation_errors: list[dict[str, str]] = []

            async def _translate_one_language(lang: str) -> tuple[str, str | None, str | None]:
                lang_code = lang.strip()
                if not lang_code:
                    return "", None, None
                try:
                    async with semaphore:
                        translated = await asyncio.to_thread(
                            translate_text_with_gemini,
                            client,
                            cfg.gemini_model,
                            "ko",
                            lang_code,
                            menu.menuName,
                        )
                    return lang_code, translated, None
                except Exception as e:
                    return lang_code, None, str(e)

            results_by_lang = await asyncio.gather(
                *[_translate_one_language(lang) for lang in payload.targetLanguages]
            )

            for lang_code, translated, error_reason in results_by_lang:
                if not lang_code:
                    continue
                if translated is not None:
                    translations.append({"langCode": lang_code, "translatedName": translated})
                    continue
                if error_reason is not None:
                    logger.warning(
                        "translation failed menuId=%s lang=%s: %s",
                        menu.menuId,
                        lang_code,
                        error_reason,
                    )
                    translation_errors.append({"langCode": lang_code, "reason": error_reason})
            return {
                "menuId": menu.menuId,
                "sourceName": menu.menuName,
                "translations": translations,
                "translationErrors": translation_errors,
            }

        results = await asyncio.gather(*[_translate_single_menu(menu) for menu in payload.menus])

        return v1_success({"results": results})

    @router.post("/translations")
    async def free_translation_v1(payload: FreeTranslationRequest, request: Request):
        try:
            validate_accept_language(request.headers.get("Accept-Language"))
        except ValueError as e:
            return _v1_bad_request(str(e))
        try:
            translated = await asyncio.to_thread(
                translate_text_with_gemini,
                client,
                cfg.gemini_model,
                payload.sourceLang,
                payload.targetLang,
                payload.text,
            )
        except Exception as e:
            return v1_error("AI_002", f"번역 실패: {e}", status_code=500)

        return v1_success(
            {
                "sourceLang": payload.sourceLang,
                "targetLang": payload.targetLang,
                "text": payload.text,
                "translatedText": translated,
            }
        )

    @router.post("/ai/menu-board/analyze")
    async def analyze_menu_board_v1(
        request: Request,
        image: UploadFile = File(...),
        requestId: str | None = Form(default=None),
    ):
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

        try:
            identified = await asyncio.to_thread(
                identify_food_from_image,
                client,
                cfg.gemini_model,
                image_bytes,
                mime_type,
            )
        except Exception as e:
            return v1_error("AI_003", f"메뉴판 이미지 분석 실패: {e}", status_code=500)

        return v1_success(
            {
                "requestId": requestId,
                "recognizedMenus": [
                    {
                        "menuName": identified.get("foodNameKo"),
                        "confidence": identified.get("confidence"),
                    }
                ],
            }
        )

    @router.post("/ai/food-images/analyze")
    async def analyze_food_image_v1(
        request: Request,
        image: UploadFile = File(...),
        requestId: str | None = Form(default=None),
    ):
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

        try:
            analysis = await asyncio.to_thread(
                analyze_food_image_bytes,
                client,
                cfg.gemini_model,
                image_bytes,
                mime_type,
            )
        except Exception as e:
            return v1_error("AI_003", f"음식 이미지 분석 실패: {e}", status_code=500)

        ingredients = []
        for item in analysis.get("추정_식재료") or []:
            if not isinstance(item, dict):
                continue
            code = map_ingredient_code(str(item.get("재료", "")).strip())
            if not code:
                continue
            ingredients.append(
                {
                    "ingredientCode": code,
                    "confidence": _safe_float(item.get("신뢰도", 0.5), default=0.5),
                }
            )
        return v1_success(
            {
                "requestId": requestId,
                "foodName": analysis.get("음식명"),
                "ingredients": ingredients,
                "notes": analysis.get("주의사항"),
            }
        )

    return router
