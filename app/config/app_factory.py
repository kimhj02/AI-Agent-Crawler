"""FastAPI app 조립 모듈."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError

from app.config.runtime import API_V1_PREFIX, RuntimeContext
from app.api.routes.live import create_legacy_router, create_v1_router
from app.api.routes.spring_native import create_spring_native_router
from app.common.service_ops import next_run, run_weekly_crawl_once, v1_error

logger = logging.getLogger(__name__)


def create_app(ctx: RuntimeContext) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async def _weekly_loop() -> None:
            tz = ZoneInfo(ctx.config.timezone_name)
            while True:
                now = datetime.now(tz)
                target = next_run(
                    now,
                    weekday=ctx.config.crawl_weekday,
                    hour=ctx.config.crawl_hour,
                    minute=ctx.config.crawl_minute,
                )
                await asyncio.sleep(max((target - now).total_seconds(), 1))
                try:
                    result = await asyncio.to_thread(run_weekly_crawl_once, ctx.config, ctx.client)
                    logger.info("weekly crawl forwarding succeeded: %s", result)
                except Exception:
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

    openapi_tags = [
        {"name": "legacy", "description": "기존 운영 호환 엔드포인트"},
        {"name": "v1-meals", "description": "식단 크롤링/조회 관련 API"},
        {"name": "v1-ai", "description": "AI 분석/이미지 분석 API"},
        {"name": "v1-translation", "description": "번역 API"},
        {
            "name": "spring-meal-client",
            "description": "Spring Boot `PythonMealClientAdapter` / `MealCrawlProperties` 기본 경로와 동일한 비래핑 JSON 응답",
        },
    ]
    app = FastAPI(
        title="AI-Agent-Crawler Live Service",
        description="Spring 연동용 Python API 서버입니다. 성공 응답은 success/data, 실패 응답은 success/code/msg 형식을 사용합니다.",
        version="1.1.0",
        lifespan=lifespan,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=openapi_tags,
    )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(request: Request, exc: RequestValidationError):
        if request.url.path.startswith(API_V1_PREFIX):
            return v1_error(
                "COM_002",
                "요청 데이터 변환 과정에서 오류가 발생했습니다.",
                status_code=400,
            )
        return await request_validation_exception_handler(request, exc)

    app.include_router(create_legacy_router(ctx))
    app.include_router(create_v1_router(ctx))
    app.include_router(create_spring_native_router(ctx))
    return app
