"""상시 구동 서비스: 주간 급식 크롤링 전송 + 실시간 이미지 분석 전송."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, AsyncIterator
from zoneinfo import ZoneInfo

import requests
from fastapi import FastAPI, File, HTTPException, Security, UploadFile
from fastapi import Body
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google import genai
from google.genai import types

import repo_env
from crawler.kumoh_menu import load_menus
from crawler.push_menus import post_menu_ingest
from food_image.agent import analyze_food_image_bytes
from menu_allergy.agent import analyze_menus_with_gemini, iter_menu_entries, results_to_dataframe
from user_features.i18n_summary import summarize_for_locale
from user_features.payloads import build_extended_menu_payload

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


WEEKDAY_TO_INDEX = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


@dataclass
class ServiceConfig:
    spring_menus_url: str | None
    spring_image_analysis_url: str | None
    spring_image_identify_url: str | None
    spring_text_analysis_url: str | None
    spring_api_token: str | None
    spring_api_key: str | None
    gemini_model: str
    weekly_menu_model: str
    i18n_locale: str
    weekly_batch_size: int
    weekly_sleep_seconds: float
    enable_direct_image_analysis: bool
    timezone_name: str
    crawl_weekday: int
    crawl_hour: int
    crawl_minute: int


def _load_config() -> ServiceConfig:
    weekday_text = os.environ.get("WEEKLY_CRAWL_DAY", "mon").strip().lower()
    if weekday_text not in WEEKDAY_TO_INDEX:
        raise RuntimeError("WEEKLY_CRAWL_DAY must be one of mon,tue,wed,thu,fri,sat,sun")

    raw_hour = os.environ.get("WEEKLY_CRAWL_HOUR", "6")
    raw_minute = os.environ.get("WEEKLY_CRAWL_MINUTE", "0")
    try:
        hour = int(raw_hour)
        minute = int(raw_minute)
    except ValueError as e:
        raise RuntimeError(
            "WEEKLY_CRAWL_HOUR/WEEKLY_CRAWL_MINUTE must be integers "
            "(hour: 0..23, minute: 0..59)"
        ) from e
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise RuntimeError("WEEKLY_CRAWL_HOUR/MINUTE out of range")

    enable_direct_image_analysis = (
        os.environ.get("ENABLE_DIRECT_IMAGE_ANALYSIS", "false").strip().lower() == "true"
    )

    return ServiceConfig(
        spring_menus_url=os.environ.get("SPRING_MENUS_URL", "").strip() or None,
        spring_image_analysis_url=os.environ.get("SPRING_IMAGE_ANALYSIS_URL", "").strip() or None,
        spring_image_identify_url=os.environ.get("SPRING_IMAGE_IDENTIFY_URL", "").strip() or None,
        spring_text_analysis_url=os.environ.get("SPRING_TEXT_ANALYSIS_URL", "").strip() or None,
        spring_api_token=os.environ.get("SPRING_API_TOKEN", "").strip() or None,
        spring_api_key=os.environ.get("SPRING_API_KEY", "").strip() or None,
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        weekly_menu_model=os.environ.get("WEEKLY_MENU_MODEL", "gemini-2.5-flash-lite"),
        i18n_locale=os.environ.get("I18N_LOCALE", "en"),
        weekly_batch_size=int(os.environ.get("WEEKLY_MENU_BATCH_SIZE", "4")),
        weekly_sleep_seconds=float(os.environ.get("WEEKLY_MENU_SLEEP_SECONDS", "21.0")),
        enable_direct_image_analysis=enable_direct_image_analysis,
        timezone_name=os.environ.get("SERVICE_TIMEZONE", "Asia/Seoul").strip() or "Asia/Seoul",
        crawl_weekday=WEEKDAY_TO_INDEX[weekday_text],
        crawl_hour=hour,
        crawl_minute=minute,
    )


def _auth_headers(token: str | None, api_key: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json; charset=utf-8", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _next_run(now: datetime, *, weekday: int, hour: int, minute: int) -> datetime:
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    days_ahead = (weekday - candidate.weekday()) % 7
    if days_ahead == 0 and candidate <= now:
        days_ahead = 7
    return candidate + timedelta(days=days_ahead)


def _run_weekly_crawl_once(cfg: ServiceConfig) -> dict[str, Any]:
    if not cfg.spring_menus_url:
        raise RuntimeError("SPRING_MENUS_URL is required for weekly crawl forwarding")
    if CLIENT is None:
        raise RuntimeError("GEMINI_API_KEY is required for weekly analysis")

    menus = load_menus()
    if not menus:
        raise RuntimeError("크롤링 결과가 비었습니다.")

    entries = iter_menu_entries(menus)
    if not entries:
        raise RuntimeError("분석할 메뉴 셀이 없습니다.")

    analysis_results = analyze_menus_with_gemini(
        CLIENT,
        cfg.weekly_menu_model,
        entries,
        batch_size=cfg.weekly_batch_size,
        sleep_between_batches_sec=cfg.weekly_sleep_seconds,
    )
    analysis_df = results_to_dataframe(analysis_results)
    i18n_rows = analysis_df.to_dict(orient="records")
    i18n_summary = summarize_for_locale(CLIENT, cfg.weekly_menu_model, i18n_rows, cfg.i18n_locale)

    payload = build_extended_menu_payload(
        menus,
        source="https://www.kumoh.ac.kr",
        analysis_df=analysis_df,
        i18n_summary=i18n_summary,
    )
    res = post_menu_ingest(
        cfg.spring_menus_url,
        payload,
        bearer_token=cfg.spring_api_token,
        api_key=cfg.spring_api_key,
        timeout=60.0,
    )
    if not res.ok:
        body = (res.text or "").strip()
        raise RuntimeError(f"메뉴 전송 실패 HTTP {res.status_code}: {body[:500]}")
    return {
        "status": "ok",
        "restaurants": len(payload.get("restaurants", [])),
        "analysisRows": len(analysis_df),
        "i18nLocale": cfg.i18n_locale,
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError("모델 응답에서 JSON 객체를 찾을 수 없습니다.")
    obj = json.loads(raw[start : end + 1])
    if not isinstance(obj, dict):
        raise RuntimeError("모델 응답 JSON이 객체 형태가 아닙니다.")
    return obj


def _analyze_food_text(name: str) -> dict[str, Any]:
    if CLIENT is None:
        raise RuntimeError("GEMINI_API_KEY is not set")
    prompt = f"""음식 이름: {name}

다음 JSON 객체 하나만 출력:
{{
  "foodNameKo": "음식 이름(한국어)",
  "ingredientsKo": ["주요 재료"],
  "allergensKo": [{{"name": "알레르기 유발 가능 식품", "reason": "근거"}}]
}}
"""
    resp = CLIENT.models.generate_content(
        model=CONFIG.gemini_model,
        contents=[prompt],
        config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=2048),
    )
    return _extract_json_object((getattr(resp, "text", "") or "").strip())


def _identify_food_from_image(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    if CLIENT is None:
        raise RuntimeError("GEMINI_API_KEY is not set")
    prompt = """이미지의 음식 이름만 식별하세요. JSON 객체 하나만 출력:
{"foodNameKo":"...", "confidence": 0.0~1.0}
"""
    resp = CLIENT.models.generate_content(
        model=CONFIG.gemini_model,
        contents=[
            types.Part.from_text(text=prompt),
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ],
        config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=512),
    )
    return _extract_json_object((getattr(resp, "text", "") or "").strip())


def _post_json(url: str, payload: dict[str, Any]) -> requests.Response:
    return requests.post(
        url,
        json=payload,
        headers=_auth_headers(CONFIG.spring_api_token, CONFIG.spring_api_key),
        timeout=60.0,
    )


repo_env.load_dotenv_from_repo_root()
CONFIG = _load_config()
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
CLIENT = genai.Client(api_key=API_KEY) if API_KEY else None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async def _weekly_loop() -> None:
        tz = ZoneInfo(CONFIG.timezone_name)
        while True:
            now = datetime.now(tz)
            target = _next_run(
                now,
                weekday=CONFIG.crawl_weekday,
                hour=CONFIG.crawl_hour,
                minute=CONFIG.crawl_minute,
            )
            await asyncio.sleep(max((target - now).total_seconds(), 1))
            try:
                result = await asyncio.to_thread(_run_weekly_crawl_once, CONFIG)
                logger.info("weekly crawl forwarding succeeded: %s", result)
            except Exception:
                # 실패 시 프로세스를 죽이지 않고 다음 주기를 기다린다.
                logger.exception("weekly crawl forwarding failed")

    app.state.weekly_task = asyncio.create_task(_weekly_loop())
    try:
        yield
    finally:
        task = getattr(app.state, "weekly_task", None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="AI-Agent-Crawler Live Service", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "weeklyCrawlConfigured": CONFIG.spring_menus_url is not None,
        "imageAnalysisConfigured": CONFIG.spring_image_analysis_url is not None,
        "imageIdentifyConfigured": CONFIG.spring_image_identify_url is not None,
        "textAnalysisConfigured": CONFIG.spring_text_analysis_url is not None,
        "directImageAnalysisEnabled": CONFIG.enable_direct_image_analysis,
        "timezone": CONFIG.timezone_name,
    }


@app.post("/crawl-and-forward")
def crawl_and_forward(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> dict[str, Any]:
    if CONFIG.spring_api_token and (
        credentials is None or credentials.credentials != CONFIG.spring_api_token
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        return _run_weekly_crawl_once(CONFIG)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/analyze-image-and-forward")
async def analyze_image_and_forward(
    image: UploadFile = File(...),
    user_id: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    if not CONFIG.enable_direct_image_analysis:
        raise HTTPException(
            status_code=403,
            detail=(
                "Direct image analysis is disabled. "
                "Set ENABLE_DIRECT_IMAGE_ANALYSIS=true to enable."
            ),
        )
    if CLIENT is None:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not set")
    if not CONFIG.spring_image_analysis_url:
        raise HTTPException(status_code=500, detail="SPRING_IMAGE_ANALYSIS_URL is not set")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="이미지 파일이 비어 있습니다.")
    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail="이미지 파일이 너무 큽니다 (최대 10MB).")

    mime_type = image.content_type or "image/jpeg"
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 이미지 형식: {mime_type}")
    try:
        analysis = await asyncio.to_thread(
            analyze_food_image_bytes, CLIENT, CONFIG.gemini_model, image_bytes, mime_type
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이미지 분석 실패: {e}") from e

    payload = {
        "requestId": request_id,
        "userId": user_id,
        "capturedAt": datetime.now(ZoneInfo(CONFIG.timezone_name)).isoformat(),
        "analysis": analysis,
    }
    try:
        res = await asyncio.to_thread(
            _post_json,
            CONFIG.spring_image_analysis_url,
            payload,
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Spring 전송 실패: {e}") from e

    if not res.ok:
        raise HTTPException(
            status_code=502,
            detail=f"Spring 응답 오류 HTTP {res.status_code}: {(res.text or '')[:500]}",
        )
    return {"status": "ok", "forwardStatus": res.status_code, "analysis": analysis}


@app.post("/analyze-food-text-and-forward")
async def analyze_food_text_and_forward(
    food_name: str = Body(..., embed=True, description="분석할 음식 이름"),
) -> dict[str, Any]:
    if not CONFIG.spring_text_analysis_url:
        raise HTTPException(status_code=500, detail="SPRING_TEXT_ANALYSIS_URL is not set")
    if not food_name.strip():
        raise HTTPException(status_code=400, detail="food_name is empty")
    try:
        analysis = await asyncio.to_thread(_analyze_food_text, food_name.strip())
        payload = {
            "foodNameInput": food_name.strip(),
            "capturedAt": datetime.now(ZoneInfo(CONFIG.timezone_name)).isoformat(),
            "analysis": analysis,
        }
        res = await asyncio.to_thread(_post_json, CONFIG.spring_text_analysis_url, payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"텍스트 음식 분석 실패: {e}") from e

    if not res.ok:
        raise HTTPException(status_code=502, detail=f"Spring 응답 오류 HTTP {res.status_code}")
    return {"status": "ok", "forwardStatus": res.status_code, "analysis": analysis}


@app.post("/identify-image-and-forward")
async def identify_image_and_forward(
    image: UploadFile = File(...),
    request_id: str | None = None,
) -> dict[str, Any]:
    if not CONFIG.spring_image_identify_url:
        raise HTTPException(status_code=500, detail="SPRING_IMAGE_IDENTIFY_URL is not set")
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="이미지 파일이 비어 있습니다.")
    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail="이미지 파일이 너무 큽니다 (최대 10MB).")
    mime_type = image.content_type or "image/jpeg"
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 이미지 형식: {mime_type}")

    try:
        identified = await asyncio.to_thread(_identify_food_from_image, image_bytes, mime_type)
        payload = {
            "requestId": request_id,
            "capturedAt": datetime.now(ZoneInfo(CONFIG.timezone_name)).isoformat(),
            "identified": identified,
        }
        res = await asyncio.to_thread(_post_json, CONFIG.spring_image_identify_url, payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이미지 음식 식별 실패: {e}") from e
    if not res.ok:
        raise HTTPException(status_code=502, detail=f"Spring 응답 오류 HTTP {res.status_code}")
    return {"status": "ok", "forwardStatus": res.status_code, "identified": identified}


