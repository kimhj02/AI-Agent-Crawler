"""상시 구동 서비스: 주간 급식 크롤링 전송 + 실시간 이미지 분석 전송."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests
from fastapi import FastAPI, File, HTTPException, UploadFile
from google import genai

import repo_env
from crawler.kumoh_menu import load_menus
from crawler.push_menus import post_menu_ingest
from crawler.spring_payload import build_menu_ingest_payload
from food_image.agent import analyze_food_image_bytes


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
    spring_image_url: str | None
    spring_api_token: str | None
    spring_api_key: str | None
    gemini_model: str
    timezone_name: str
    crawl_weekday: int
    crawl_hour: int
    crawl_minute: int


def _load_config() -> ServiceConfig:
    weekday_text = os.environ.get("WEEKLY_CRAWL_DAY", "mon").strip().lower()
    if weekday_text not in WEEKDAY_TO_INDEX:
        raise RuntimeError("WEEKLY_CRAWL_DAY must be one of mon,tue,wed,thu,fri,sat,sun")

    hour = int(os.environ.get("WEEKLY_CRAWL_HOUR", "6"))
    minute = int(os.environ.get("WEEKLY_CRAWL_MINUTE", "0"))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise RuntimeError("WEEKLY_CRAWL_HOUR/MINUTE out of range")

    return ServiceConfig(
        spring_menus_url=os.environ.get("SPRING_MENUS_URL", "").strip() or None,
        spring_image_url=os.environ.get("SPRING_IMAGE_ANALYSIS_URL", "").strip() or None,
        spring_api_token=os.environ.get("SPRING_API_TOKEN", "").strip() or None,
        spring_api_key=os.environ.get("SPRING_API_KEY", "").strip() or None,
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
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

    menus = load_menus()
    if not menus:
        raise RuntimeError("크롤링 결과가 비었습니다.")

    payload = build_menu_ingest_payload(menus, source="https://www.kumoh.ac.kr")
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
    return {"status": "ok", "restaurants": len(payload.get("restaurants", []))}


app = FastAPI(title="AI-Agent-Crawler Live Service")
repo_env.load_dotenv_from_repo_root()
CONFIG = _load_config()
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
CLIENT = genai.Client(api_key=API_KEY) if API_KEY else None


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "weeklyCrawlTarget": CONFIG.spring_menus_url,
        "imageAnalysisTarget": CONFIG.spring_image_url,
        "timezone": CONFIG.timezone_name,
    }


@app.post("/crawl-and-forward")
def crawl_and_forward() -> dict[str, Any]:
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
    if CLIENT is None:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not set")
    if not CONFIG.spring_image_url:
        raise HTTPException(status_code=500, detail="SPRING_IMAGE_ANALYSIS_URL is not set")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="이미지 파일이 비어 있습니다.")

    mime_type = image.content_type or "image/jpeg"
    try:
        analysis = analyze_food_image_bytes(CLIENT, CONFIG.gemini_model, image_bytes, mime_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이미지 분석 실패: {e}") from e

    payload = {
        "requestId": request_id,
        "userId": user_id,
        "capturedAt": datetime.now(ZoneInfo(CONFIG.timezone_name)).isoformat(),
        "analysis": analysis,
    }
    try:
        res = requests.post(
            CONFIG.spring_image_url,
            json=payload,
            headers=_auth_headers(CONFIG.spring_api_token, CONFIG.spring_api_key),
            timeout=60.0,
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Spring 전송 실패: {e}") from e

    if not res.ok:
        raise HTTPException(
            status_code=502,
            detail=f"Spring 응답 오류 HTTP {res.status_code}: {(res.text or '')[:500]}",
        )
    return {"status": "ok", "forwardStatus": res.status_code, "analysis": analysis}


@app.on_event("startup")
async def start_scheduler() -> None:
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
                _run_weekly_crawl_once(CONFIG)
            except Exception as e:
                # 실패 시 프로세스를 죽이지 않고 다음 주기를 기다린다.
                print(f"[weekly-crawl] failed: {e}", flush=True)

    app.state.weekly_task = asyncio.create_task(_weekly_loop())


@app.on_event("shutdown")
async def stop_scheduler() -> None:
    task = getattr(app.state, "weekly_task", None)
    if task:
        task.cancel()
