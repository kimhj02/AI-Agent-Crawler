"""`/api/v1` 요청 DTO 모음."""

from __future__ import annotations

from datetime import date
from typing import Any, Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, Field, model_validator

T = TypeVar("T")


class PythonMealCrawlRequest(BaseModel):
    schoolName: str = Field(..., min_length=1)
    cafeteriaName: str = Field(..., min_length=1)
    sourceUrl: str = Field(..., min_length=1)
    startDate: date
    endDate: date

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.startDate > self.endDate:
            raise ValueError("startDate는 endDate보다 이후일 수 없습니다.")
        return self


class PythonMenuAnalysisTargetDto(BaseModel):
    menuId: int
    menuName: str = Field(..., min_length=1)


class PythonMenuAnalysisRequest(BaseModel):
    menus: list[PythonMenuAnalysisTargetDto] = Field(..., min_length=1)


class PythonMenuTranslationTargetDto(BaseModel):
    menuId: int
    menuName: str = Field(..., min_length=1)


class PythonMenuTranslationRequest(BaseModel):
    menus: list[PythonMenuTranslationTargetDto] = Field(..., min_length=1)
    targetLanguages: list[str] = Field(..., min_length=1)


class FreeTranslationRequest(BaseModel):
    sourceLang: str = Field(..., min_length=2)
    targetLang: str = Field(..., min_length=2)
    text: str = Field(..., min_length=1)


class ApiErrorResponse(BaseModel):
    success: bool = Field(default=False, examples=[False])
    code: str = Field(..., examples=["COM_002"])
    msg: str = Field(..., examples=["요청 데이터 변환 과정에서 오류가 발생했습니다."])


class ApiSuccessResponse(BaseModel, Generic[T]):
    success: bool = Field(default=True, examples=[True])
    data: T


class MealMenuItemResponse(BaseModel):
    cornerName: str
    displayOrder: int
    menuName: str


class MealItemResponse(BaseModel):
    mealDate: str
    mealType: str
    menus: list[MealMenuItemResponse]


class PythonMealCrawlDataResponse(BaseModel):
    schoolName: str
    cafeteriaName: str
    sourceUrl: str
    startDate: str
    endDate: str
    meals: list[MealItemResponse]


class IngredientItemResponse(BaseModel):
    ingredientCode: str
    confidence: float


class MenuAnalysisResultResponse(BaseModel):
    menuId: int
    menuName: str
    status: str
    reason: Optional[str]
    modelName: str
    modelVersion: str
    analyzedAt: str
    ingredients: list[IngredientItemResponse]


class PythonMenuAnalysisDataResponse(BaseModel):
    results: list[MenuAnalysisResultResponse]


class TranslationItemResponse(BaseModel):
    langCode: str
    translatedName: str


class TranslationErrorItemResponse(BaseModel):
    langCode: str
    reason: str


class MenuTranslationResultResponse(BaseModel):
    menuId: int
    sourceName: str
    translations: list[TranslationItemResponse]
    translationErrors: list[TranslationErrorItemResponse]


class PythonMenuTranslationDataResponse(BaseModel):
    results: list[MenuTranslationResultResponse]


class FreeTranslationDataResponse(BaseModel):
    sourceLang: str
    targetLang: str
    text: str
    translatedText: str


class RecognizedMenuItemResponse(BaseModel):
    menuName: Optional[str]
    confidence: Optional[float]


class MenuBoardAnalyzeDataResponse(BaseModel):
    requestId: Optional[str]
    recognizedMenus: list[RecognizedMenuItemResponse]


class FoodImageAnalyzeDataResponse(BaseModel):
    requestId: Optional[str]
    foodName: Optional[str]
    ingredients: list[IngredientItemResponse]
    notes: Optional[str]


class LegacyHealthResponse(BaseModel):
    ok: bool
    weeklyCrawlConfigured: bool
    imageAnalysisConfigured: bool
    imageIdentifyConfigured: bool
    textAnalysisConfigured: bool
    directImageAnalysisEnabled: bool
    timezone: str


class LegacyForwardResponse(BaseModel):
    status: str
    forwardStatus: int
    analysis: Optional[dict[str, Any]] = None
    identified: Optional[dict[str, Any]] = None


class LegacyCrawlForwardResponse(BaseModel):
    status: str
    restaurants: int
    analysisRows: int
    i18nLocale: str


class LoginRequest(BaseModel):
    idToken: str = Field(..., min_length=1)
    deviceId: str = Field(..., min_length=1)


class RefreshTokenRequest(BaseModel):
    refreshToken: str = Field(..., min_length=1)


class LogoutRequest(BaseModel):
    refreshToken: str = Field(..., min_length=1)


class UpdateAllergiesRequest(BaseModel):
    allergyCodes: list[str] = Field(..., min_length=0)


class UpdateLanguageRequest(BaseModel):
    languageCode: str = Field(..., min_length=1)


class UpdateReligionRequest(BaseModel):
    religiousCode: Optional[Literal["HALAL", "VEGAN"]] = None


class CompleteOnboardingRequest(BaseModel):
    languageCode: str = Field(..., min_length=1)
    schoolId: int
    allergyCodes: list[str] = Field(default_factory=list)
    religiousCode: Optional[str] = None


class LoginDataResponse(BaseModel):
    accessToken: str = Field(..., examples=["access-token"])
    refreshToken: str = Field(..., examples=["refresh-token"])
    expiresIn: int = Field(..., examples=[3600])
    refreshExpiresIn: int = Field(..., examples=[1209600])
    onboardingCompleted: bool = Field(..., examples=[False])


class LogoutDataResponse(BaseModel):
    pass


class AllergiesDataResponse(BaseModel):
    allergyCodes: list[Literal["EGG", "MILK", "PEANUT", "SOYBEAN", "WHEAT"]] = Field(
        default_factory=list,
        examples=[["EGG", "MILK"]],
    )


class LanguageDataResponse(BaseModel):
    languageCode: Literal["ko", "en", "ja", "zh-CN", "vi"] = Field(..., examples=["en"])


class ReligionDataResponse(BaseModel):
    religiousCode: Optional[Literal["HALAL", "VEGAN"]] = Field(default=None, examples=["HALAL"])


class LanguageOptionItemResponse(BaseModel):
    languageCode: Literal["ko", "en", "ja", "zh-CN", "vi"] = Field(..., examples=["en"])
    languageName: str = Field(..., examples=["English"])


class AllergyOptionItemResponse(BaseModel):
    allergyCode: Literal["EGG", "MILK", "PEANUT", "SOYBEAN", "WHEAT"] = Field(..., examples=["EGG"])
    allergyName: str = Field(..., examples=["Egg"])


class ReligionOptionItemResponse(BaseModel):
    religiousCode: Literal["HALAL", "VEGAN"] = Field(..., examples=["HALAL"])
    religiousName: str = Field(..., examples=["Halal"])


class LanguageOptionsDataResponse(BaseModel):
    languages: list[LanguageOptionItemResponse]


class AllergyOptionsDataResponse(BaseModel):
    allergies: list[AllergyOptionItemResponse]


class ReligionOptionsDataResponse(BaseModel):
    religions: list[ReligionOptionItemResponse]


class SchoolResponse(BaseModel):
    schoolId: int = Field(..., examples=[1])
    schoolName: str = Field(..., examples=["금오공과대학교"])


class SchoolsDataResponse(BaseModel):
    schools: list[SchoolResponse]


class OnboardingCompleteDataResponse(BaseModel):
    languageCode: Literal["ko", "en", "ja", "zh-CN", "vi"] = Field(..., examples=["en"])
    schoolId: int = Field(..., examples=[1])
    allergyCodes: list[Literal["EGG", "MILK", "PEANUT", "SOYBEAN", "WHEAT"]] = Field(
        default_factory=list,
        examples=[["EGG", "MILK"]],
    )
    religiousCode: Optional[Literal["HALAL", "VEGAN"]] = Field(default=None, examples=["HALAL"])
    onboardingCompleted: bool = Field(..., examples=[True])


class CafeteriaItemResponse(BaseModel):
    cafeteriaId: int = Field(..., examples=[1])
    cafeteriaName: str = Field(..., examples=["학생식당"])


class CafeteriasDataResponse(BaseModel):
    schoolId: int = Field(..., examples=[1])
    cafeterias: list[CafeteriaItemResponse]


class MealMenuResponse(BaseModel):
    cornerName: str = Field(..., examples=["중식"])
    displayOrder: int = Field(..., examples=[1])
    menuName: str = Field(..., examples=["김치찌개"])


class MealScheduleResponse(BaseModel):
    mealDate: str = Field(..., examples=["2026-04-27"])
    mealType: str = Field(..., examples=["LUNCH"])
    menus: list[MealMenuResponse]


class WeeklyMealsDataResponse(BaseModel):
    schoolId: int = Field(..., examples=[1])
    cafeteriaId: int = Field(..., examples=[1])
    weekStartDate: str = Field(..., examples=["2026-04-27"])
    weekEndDate: str = Field(..., examples=["2026-05-03"])
    mealSchedules: list[MealScheduleResponse]
