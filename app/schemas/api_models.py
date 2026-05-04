"""`/api/v1` 요청 DTO 모음."""

from __future__ import annotations

from datetime import date
from typing import Any, Generic, Optional, TypeVar

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
    reason: Optional[str] = None
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
    menuName: Optional[str] = None
    confidence: Optional[float] = None


class MenuBoardAnalyzeDataResponse(BaseModel):
    requestId: Optional[str] = None
    recognizedMenus: list[RecognizedMenuItemResponse]


class FoodImageAnalyzeDataResponse(BaseModel):
    requestId: Optional[str] = None
    foodName: Optional[str] = None
    ingredients: list[IngredientItemResponse]
    notes: Optional[str] = None


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
