"""Spring Swagger 호환 라우터 레이어."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

import requests
from fastapi import APIRouter, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.runtime import RuntimeContext
from app.dto.api_models import (
    AllergyOptionsDataResponse,
    AllergiesDataResponse,
    ApiErrorResponse,
    ApiSuccessResponse,
    CafeteriasDataResponse,
    LanguageDataResponse,
    LanguageOptionsDataResponse,
    LoginDataResponse,
    CompleteOnboardingRequest,
    LoginRequest,
    OnboardingCompleteDataResponse,
    LogoutRequest,
    ReligionDataResponse,
    ReligionOptionsDataResponse,
    RefreshTokenRequest,
    SchoolsDataResponse,
    UpdateAllergiesRequest,
    UpdateLanguageRequest,
    UpdateReligionRequest,
    WeeklyMealsDataResponse,
)
from app.service.live_service import LiveService
from app.util.service_ops import CrawlSourceUpstreamError, v1_error, v1_success

security = HTTPBearer(auto_error=False)

DEFAULT_SOURCE_URL = "https://www.kumoh.ac.kr/ko/restaurant01.do"
DEFAULT_CAFETERIAS = [
    {"cafeteriaId": 1, "cafeteriaName": "학생식당"},
    {"cafeteriaId": 2, "cafeteriaName": "교직원식당"},
    {"cafeteriaId": 3, "cafeteriaName": "분식당"},
]
LANGUAGE_OPTIONS = [
    {"languageCode": "ko", "languageName": "한국어"},
    {"languageCode": "en", "languageName": "English"},
    {"languageCode": "ja", "languageName": "日本語"},
    {"languageCode": "zh-CN", "languageName": "简体中文"},
    {"languageCode": "vi", "languageName": "Tiếng Việt"},
]
ALLERGY_OPTIONS = [
    {"allergyCode": "EGG", "allergyName": "Egg"},
    {"allergyCode": "MILK", "allergyName": "Milk"},
    {"allergyCode": "PEANUT", "allergyName": "Peanut"},
    {"allergyCode": "SOYBEAN", "allergyName": "Soybean"},
    {"allergyCode": "WHEAT", "allergyName": "Wheat"},
]
RELIGION_OPTIONS = [
    {"religiousCode": "HALAL", "religiousName": "Halal"},
    {"religiousCode": "VEGAN", "religiousName": "Vegan"},
]
SCHOOLS = [{"schoolId": 1, "schoolName": "금오공과대학교"}]
VALID_LANGS = {x["languageCode"] for x in LANGUAGE_OPTIONS}
VALID_ALLERGIES = {x["allergyCode"] for x in ALLERGY_OPTIONS}
VALID_RELIGIONS = {x["religiousCode"] for x in RELIGION_OPTIONS}

_USER_SETTINGS: dict[str, dict[str, Any]] = {}


def _user_key(credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[str]:
    if credentials is None or not credentials.credentials:
        return None
    return credentials.credentials.strip()


def _require_user(credentials: Optional[HTTPAuthorizationCredentials]):
    key = _user_key(credentials)
    if not key:
        return None, v1_error("AUTH_001", "인증이 필요합니다.", status_code=401)
    state = _USER_SETTINGS.setdefault(
        key,
        {
            "languageCode": "en",
            "allergyCodes": [],
            "religiousCode": None,
            "schoolId": 1,
            "onboardingCompleted": False,
        },
    )
    return state, None


def create_spring_compat_router(ctx: RuntimeContext) -> APIRouter:
    if not ctx.config.spring_compat_stub_mode:
        router = APIRouter(tags=["spring-compat"])

        @router.get("/spring-compat-disabled", summary="Spring 호환 스텁 비활성화 안내")
        def spring_compat_disabled():
            return v1_error(
                "COM_003",
                "SPRING_COMPAT_STUB_MODE=true 일 때만 Spring 호환 스텁 API를 사용할 수 있습니다.",
                status_code=503,
            )

        return router

    service = LiveService(ctx)
    router = APIRouter(tags=["spring-compat"])

    @router.post(
        "/auth/login",
        summary="구글 로그인",
        response_model=ApiSuccessResponse[LoginDataResponse],
        responses={400: {"model": ApiErrorResponse}, 401: {"model": ApiErrorResponse}},
    )
    def login(payload: LoginRequest):
        data = {
            "accessToken": f"access-{payload.deviceId}",
            "refreshToken": f"refresh-{payload.deviceId}",
            "expiresIn": 3600,
            "refreshExpiresIn": 1209600,
            "onboardingCompleted": False,
        }
        return v1_success(data)

    @router.post(
        "/auth/refresh",
        summary="토큰 재발급",
        response_model=ApiSuccessResponse[LoginDataResponse],
        responses={400: {"model": ApiErrorResponse}, 401: {"model": ApiErrorResponse}},
    )
    def refresh(payload: RefreshTokenRequest):
        data = {
            "accessToken": f"access-refreshed-{payload.refreshToken[:8]}",
            "refreshToken": f"refresh-refreshed-{payload.refreshToken[:8]}",
            "expiresIn": 3600,
            "refreshExpiresIn": 1209600,
            "onboardingCompleted": True,
        }
        return v1_success(data)

    @router.post(
        "/auth/logout",
        summary="로그아웃",
        response_model=ApiSuccessResponse[None],
        responses={401: {"model": ApiErrorResponse}},
    )
    def logout(payload: LogoutRequest, credentials: Optional[HTTPAuthorizationCredentials] = Security(security)):
        _, err = _require_user(credentials)
        if err:
            return err
        if not payload.refreshToken:
            return v1_error("AUTH_007", "RefreshToken이 존재하지 않습니다.", status_code=401)
        return v1_success(None)

    @router.get(
        "/api/v1/settings/allergies",
        summary="내 알레르기 설정 조회",
        response_model=ApiSuccessResponse[AllergiesDataResponse],
        responses={401: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
    )
    def get_allergies(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)):
        state, err = _require_user(credentials)
        if err:
            return err
        return v1_success({"allergyCodes": state["allergyCodes"]})

    @router.put(
        "/api/v1/settings/allergies",
        summary="알레르기 설정 변경",
        response_model=ApiSuccessResponse[AllergiesDataResponse],
        responses={400: {"model": ApiErrorResponse}, 401: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
    )
    def update_allergies(
        payload: UpdateAllergiesRequest,
        credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    ):
        state, err = _require_user(credentials)
        if err:
            return err
        if any(code not in VALID_ALLERGIES for code in payload.allergyCodes):
            return v1_error("USER_018", "알레르기 코드가 올바르지 않습니다.", status_code=400)
        state["allergyCodes"] = payload.allergyCodes
        return v1_success({"allergyCodes": state["allergyCodes"]})

    @router.get(
        "/api/v1/settings/language",
        summary="내 언어 설정 조회",
        response_model=ApiSuccessResponse[LanguageDataResponse],
        responses={401: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
    )
    def get_language(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)):
        state, err = _require_user(credentials)
        if err:
            return err
        return v1_success({"languageCode": state["languageCode"]})

    @router.patch(
        "/api/v1/settings/language",
        summary="언어 설정 변경",
        response_model=ApiSuccessResponse[LanguageDataResponse],
        responses={400: {"model": ApiErrorResponse}, 401: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
    )
    def update_language(
        payload: UpdateLanguageRequest,
        credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    ):
        state, err = _require_user(credentials)
        if err:
            return err
        if payload.languageCode not in VALID_LANGS:
            return v1_error("USER_017", "언어 코드가 올바르지 않습니다.", status_code=400)
        state["languageCode"] = payload.languageCode
        return v1_success({"languageCode": state["languageCode"]})

    @router.get(
        "/api/v1/settings/religion",
        summary="내 종교별 식이 제한 설정 조회",
        response_model=ApiSuccessResponse[ReligionDataResponse],
        responses={401: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
    )
    def get_religion(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)):
        state, err = _require_user(credentials)
        if err:
            return err
        return v1_success({"religiousCode": state["religiousCode"]})

    @router.patch(
        "/api/v1/settings/religion",
        summary="종교별 식이 제한 설정 변경",
        response_model=ApiSuccessResponse[ReligionDataResponse],
        responses={400: {"model": ApiErrorResponse}, 401: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
    )
    def update_religion(
        payload: UpdateReligionRequest,
        credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    ):
        state, err = _require_user(credentials)
        if err:
            return err
        if payload.religiousCode is not None and payload.religiousCode not in VALID_RELIGIONS:
            return v1_error("USER_019", "종교적 식이 제한 코드가 올바르지 않습니다.", status_code=400)
        state["religiousCode"] = payload.religiousCode
        return v1_success({"religiousCode": state["religiousCode"]})

    @router.get(
        "/api/v1/settings/options/languages",
        summary="언어 전체 선택지 조회",
        response_model=ApiSuccessResponse[LanguageOptionsDataResponse],
        responses={401: {"model": ApiErrorResponse}},
    )
    def get_language_options(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)):
        _, err = _require_user(credentials)
        if err:
            return err
        return v1_success({"languages": LANGUAGE_OPTIONS})

    @router.get(
        "/api/v1/settings/options/allergies",
        summary="알레르기 전체 선택지 조회",
        response_model=ApiSuccessResponse[AllergyOptionsDataResponse],
        responses={401: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
    )
    def get_allergy_options(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)):
        _, err = _require_user(credentials)
        if err:
            return err
        return v1_success({"allergies": ALLERGY_OPTIONS})

    @router.get(
        "/api/v1/settings/options/religions",
        summary="종교별 음식 제한 전체 선택지 조회",
        response_model=ApiSuccessResponse[ReligionOptionsDataResponse],
        responses={401: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
    )
    def get_religion_options(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)):
        _, err = _require_user(credentials)
        if err:
            return err
        return v1_success({"religions": RELIGION_OPTIONS})

    @router.get(
        "/api/v1/onboarding/schools",
        summary="온보딩 학교 목록 조회",
        response_model=ApiSuccessResponse[SchoolsDataResponse],
    )
    def get_schools(lang: Optional[str] = Query(default=None)):
        _ = lang
        return v1_success({"schools": SCHOOLS})

    @router.post(
        "/api/v1/onboarding/complete",
        summary="온보딩 정보 저장",
        response_model=ApiSuccessResponse[OnboardingCompleteDataResponse],
        responses={400: {"model": ApiErrorResponse}, 401: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
    )
    def complete_onboarding(
        payload: CompleteOnboardingRequest,
        credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    ):
        state, err = _require_user(credentials)
        if err:
            return err
        if payload.languageCode not in VALID_LANGS:
            return v1_error("USER_017", "언어 코드가 올바르지 않습니다.", status_code=400)
        if any(code not in VALID_ALLERGIES for code in payload.allergyCodes):
            return v1_error("USER_018", "알레르기 코드가 올바르지 않습니다.", status_code=400)
        if payload.religiousCode is not None and payload.religiousCode not in VALID_RELIGIONS:
            return v1_error("USER_019", "종교적 식이 제한 코드가 올바르지 않습니다.", status_code=400)
        state.update(
            {
                "languageCode": payload.languageCode,
                "schoolId": payload.schoolId,
                "allergyCodes": payload.allergyCodes,
                "religiousCode": payload.religiousCode,
                "onboardingCompleted": True,
            }
        )
        return v1_success(
            {
                "languageCode": state["languageCode"],
                "schoolId": state["schoolId"],
                "allergyCodes": state["allergyCodes"],
                "religiousCode": state["religiousCode"],
                "onboardingCompleted": state["onboardingCompleted"],
            }
        )

    @router.get(
        "/api/v1/mealcrawl/cafeterias",
        summary="현재 사용자 학교 식당 목록 조회",
        response_model=ApiSuccessResponse[CafeteriasDataResponse],
        responses={400: {"model": ApiErrorResponse}, 401: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
    )
    def get_cafeterias(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)):
        state, err = _require_user(credentials)
        if err:
            return err
        return v1_success({"schoolId": state["schoolId"], "cafeterias": DEFAULT_CAFETERIAS})

    @router.get(
        "/api/v1/mealcrawl/weekly-meals",
        summary="사용자 주간 식단 조회",
        response_model=ApiSuccessResponse[WeeklyMealsDataResponse],
        responses={400: {"model": ApiErrorResponse}, 401: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
    )
    def get_weekly_meals(
        cafeteriaId: int = Query(...),
        weekStartDate: date = Query(...),
        credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    ):
        state, err = _require_user(credentials)
        if err:
            return err
        cafeteria_name = next(
            (c["cafeteriaName"] for c in DEFAULT_CAFETERIAS if c["cafeteriaId"] == cafeteriaId),
            None,
        )
        if cafeteria_name is None:
            return v1_error("COM_002", "요청 데이터 변환 과정에서 오류가 발생했습니다.", status_code=400)
        try:
            table = service.load_menu_table_for_source(cafeteria_name, DEFAULT_SOURCE_URL)
        except RuntimeError:
            return v1_error("PYM_400", "요청 식단 조회 조건이 유효하지 않거나 데이터가 없습니다.", status_code=400)
        except (CrawlSourceUpstreamError, requests.exceptions.RequestException, OSError):
            return v1_error("PYM_502", "외부 크롤링 소스 조회에 실패했습니다. 잠시 후 다시 시도해주세요.", status_code=502)
        week_end = weekStartDate + timedelta(days=6)
        meals = service.build_daily_meals(
            cafeteria_name=cafeteria_name,
            table=table,
            start=weekStartDate,
            end=week_end,
        )
        return v1_success(
            {
                "schoolId": state["schoolId"],
                "cafeteriaId": cafeteriaId,
                "weekStartDate": weekStartDate.isoformat(),
                "weekEndDate": week_end.isoformat(),
                "mealSchedules": meals,
            }
        )

    return router
