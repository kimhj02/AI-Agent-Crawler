# AI-Agent-Crawler

Gemini API와 Python으로 금오공대 급식표를 수집/분석하고, Spring Boot와 연동하는 서비스입니다.

## 현재 구조 (최신)

`app` 패키지 아래에 **진입 조립(`config`) / HTTP(`api`) / 스키마 / 서비스 / 저장소 / 도메인 / 공통**을 두고, `scripts`·`tests`·`user_features`는 그대로 둡니다.

| 경로 | 설명 |
|------|------|
| `main.py` | Uvicorn 진입점 (`uvicorn main:app`) |
| `app/config` | 런타임 설정, FastAPI 앱 팩토리 |
| `app/api/routes` | HTTP 라우터(FastAPI): `live`, `spring_native`, `spring_compat` |
| `app/schemas` | Pydantic 요청·응답 모델, OpenAPI 예시 |
| `app/services` | 유스케이스(`live_service`)·순수 로직(`ops`) |
| `app/repositories` | 외부 I/O(Gemini, 크롤, Spring HTTP) |
| `app/domain` | 도메인 로직(crawler / image / allergy) |
| `app/common` | 공통 유틸·`service_ops` 재노출 |
| `scripts` | CLI·스모크 |
| `tests` | pytest (`live`, `integration`) |
| `user_features` | 확장·앱 인스턴스 조립(`live_service.py`) |

### Spring 기본 경로와 동일한 API

`mealguide.mealcrawl` 기본값과 맞춘 **비래핑 JSON** 엔드포인트(성공 시 `success`/`data` 없음):

- `POST /api/v1/crawl/meals`
- `POST /api/v1/menus/analyze`
- `POST /api/v1/menus/translate`

기존 OpenAPI용 래핑 API는 `POST /api/v1/python/...` 그대로 유지됩니다.


## 최근 변경 요약

- `crawler`, `food_image`, `menu_allergy` 루트 모듈을 `app/domain/*`으로 통합
- 계층 구조를 스프링식 단수 폴더(`config/controller/service/repository`)로 정리
- 레거시 `user_features/live/*` 구현 파일 제거
- Swagger/OpenAPI 계약 강화(`success/data`, `success/code/msg` 포맷 명시)

## 빠른 시작

```bash
pip install -r requirements.txt
cp .env.example .env
```

필수 환경변수:

```bash
GEMINI_API_KEY=...
SPRING_MENUS_URL=http://localhost:8080/api/menus/ingest
SPRING_IMAGE_IDENTIFY_URL=http://localhost:8080/api/image-identify/ingest
SPRING_TEXT_ANALYSIS_URL=http://localhost:8080/api/food-analysis/ingest
```

## 서버 실행

```bash
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
# 또는 (동일 앱 인스턴스)
python3 -m uvicorn user_features.live_service:app --host 0.0.0.0 --port 8000
```

상태 확인:

```bash
curl http://localhost:8000/health
```

Swagger/OpenAPI:

```bash
open http://localhost:8000/docs
curl http://localhost:8000/openapi.json
```

## API 규칙

- Base URL: `/api/v1`
- 성공 응답:

```json
{
  "success": true,
  "data": {}
}
```

- 실패 응답:

```json
{
  "success": false,
  "code": "COM_002",
  "msg": "요청 데이터 변환 과정에서 오류가 발생했습니다."
}
```

핵심 API:

- `POST /api/v1/python/meals/crawl`
- `POST /api/v1/python/menus/analyze`
- `POST /api/v1/python/menus/translate`
- `POST /api/v1/translations`
- `POST /api/v1/ai/menu-board/analyze`
- `POST /api/v1/ai/food-images/analyze`

비활성화된 호환 라우터:

- `spring-compat` 라우터 코드는 유지되지만 기본 설정에서는 비활성화됩니다.
- 활성화가 필요할 때만 `ENABLE_SPRING_COMPAT_ROUTER=true`로 실행하세요.
- 스텁 엔드포인트까지 열어야 할 때는 `SPRING_COMPAT_STUB_MODE=true`를 함께 설정하세요.

## API 명세

### 1) `POST /api/v1/python/meals/crawl`

- 용도: 학교/식당/기간 기준으로 식단 크롤링
- 요청 `Content-Type`: `application/json`
- 권장 헤더: `Accept-Language: ko`

요청 예시 (`curl`):

```bash
curl -sS -X POST "http://localhost:8000/api/v1/python/meals/crawl" \
  -H "Content-Type: application/json" \
  -H "Accept-Language: ko" \
  -d '{
    "schoolName": "금오공과대학교",
    "cafeteriaName": "학생식당",
    "sourceUrl": "https://www.kumoh.ac.kr/ko/restaurant01.do",
    "startDate": "2026-04-21",
    "endDate": "2026-04-27"
  }'
```

요청 본문 예시:

```json
{
  "schoolName": "금오공과대학교",
  "cafeteriaName": "학생식당",
  "sourceUrl": "https://www.kumoh.ac.kr/ko/restaurant01.do",
  "startDate": "2026-04-21",
  "endDate": "2026-04-27"
}
```

성공 응답 예시 (`meals`는 일자·끼니별로 채워질 수 있음):

```json
{
  "success": true,
  "data": {
    "schoolName": "금오공과대학교",
    "cafeteriaName": "학생식당",
    "sourceUrl": "https://www.kumoh.ac.kr/ko/restaurant01.do",
    "startDate": "2026-04-21",
    "endDate": "2026-04-27",
    "meals": [
      {
        "mealDate": "2026-04-21",
        "mealType": "LUNCH",
        "menus": [
          {"cornerName": "학생식당", "displayOrder": 1, "menuName": "김치찌개"},
          {"cornerName": "학생식당", "displayOrder": 2, "menuName": "된장찌개"}
        ]
      }
    ]
  }
}
```

실패 응답 예시 (외부 소스 조회 실패, HTTP 502):

```json
{
  "success": false,
  "code": "PYM_502",
  "msg": "외부 크롤링 소스 조회에 실패했습니다. 잠시 후 다시 시도해주세요."
}
```

실패 응답 예시 (조건 불가, HTTP 400):

```json
{
  "success": false,
  "code": "PYM_400",
  "msg": "요청 식단 조회 조건이 유효하지 않거나 데이터가 없습니다."
}
```

주요 실패 코드: `COM_002`, `PYM_400`, `PYM_502`, `PYM_500`

### 2) `POST /api/v1/python/menus/analyze`

- 용도: 메뉴 텍스트를 AI로 분석해 재료 코드 추정
- 요청 `Content-Type`: `application/json`

요청 예시 (`curl`):

```bash
curl -sS -X POST "http://localhost:8000/api/v1/python/menus/analyze" \
  -H "Content-Type: application/json" \
  -H "Accept-Language: ko" \
  -d '{"menus":[{"menuId":101,"menuName":"김치찌개"}]}'
```

요청 본문 예시:

```json
{
  "menus": [
    {"menuId": 101, "menuName": "김치찌개"}
  ]
}
```

성공 응답 예시:

```json
{
  "success": true,
  "data": {
    "results": [
      {
        "menuId": 101,
        "menuName": "김치찌개",
        "status": "COMPLETED",
        "reason": null,
        "modelName": "gemini",
        "modelVersion": "gemini-2.5-flash",
        "analyzedAt": "2026-04-27T12:00:00",
        "ingredients": [
          {"ingredientCode": "SOYBEAN", "confidence": 0.88},
          {"ingredientCode": "WHEAT", "confidence": 0.81}
        ]
      }
    ]
  }
}
```

실패 응답 예시 (`GEMINI_API_KEY` 미설정, HTTP 500):

```json
{
  "success": false,
  "code": "AI_001",
  "msg": "GEMINI_API_KEY is not set"
}
```

주요 실패 코드: `COM_002`, `AI_001`

### 3) `POST /api/v1/python/menus/translate`

- 용도: 메뉴명을 다국어로 번역
- 요청 `Content-Type`: `application/json`

요청 예시 (`curl`):

```bash
curl -sS -X POST "http://localhost:8000/api/v1/python/menus/translate" \
  -H "Content-Type: application/json" \
  -H "Accept-Language: ko" \
  -d '{"menus":[{"menuId":101,"menuName":"김치찌개"}],"targetLanguages":["en","ja"]}'
```

요청 본문 예시:

```json
{
  "menus": [
    {"menuId": 101, "menuName": "김치찌개"}
  ],
  "targetLanguages": ["en", "ja"]
}
```

성공 응답 예시:

```json
{
  "success": true,
  "data": {
    "results": [
      {
        "menuId": 101,
        "sourceName": "김치찌개",
        "translations": [
          {"langCode": "en", "translatedName": "Kimchi stew"},
          {"langCode": "ja", "translatedName": "キムチチゲ"}
        ],
        "translationErrors": []
      }
    ]
  }
}
```

실패 응답 예시 (`GEMINI_API_KEY` 미설정, HTTP 500):

```json
{
  "success": false,
  "code": "AI_001",
  "msg": "GEMINI_API_KEY is not set"
}
```

주요 실패 코드: `COM_002`, `AI_001`

### 4) `POST /api/v1/translations`

- 용도: 자유 문장 번역
- 요청 `Content-Type`: `application/json`

요청 예시 (`curl`):

```bash
curl -sS -X POST "http://localhost:8000/api/v1/translations" \
  -H "Content-Type: application/json" \
  -H "Accept-Language: ko" \
  -d '{"sourceLang":"ko","targetLang":"en","text":"이 음식에 밀가루가 들어가나요?"}'
```

요청 본문 예시:

```json
{
  "sourceLang": "ko",
  "targetLang": "en",
  "text": "이 음식에 밀가루가 들어가나요?"
}
```

성공 응답 예시:

```json
{
  "success": true,
  "data": {
    "sourceLang": "ko",
    "targetLang": "en",
    "text": "이 음식에 밀가루가 들어가나요?",
    "translatedText": "Does this dish contain flour?"
  }
}
```

주요 실패 코드: `COM_002`, `AI_002`

### 5) `POST /api/v1/ai/menu-board/analyze`

- 용도: 메뉴판 이미지에서 메뉴명 인식
- 요청 `Content-Type`: `multipart/form-data`
- 폼 필드:
  - `image`: 이미지 파일
  - `requestId`: 선택

요청 예시 (`curl`, 로컬 이미지 경로는 환경에 맞게 변경):

```bash
curl -sS -X POST "http://localhost:8000/api/v1/ai/menu-board/analyze" \
  -H "Accept-Language: ko" \
  -F "image=@./sample-menu-board.jpg" \
  -F "requestId=req-001"
```

성공 응답 예시:

```json
{
  "success": true,
  "data": {
    "requestId": "req-001",
    "recognizedMenus": [
      {"menuName": "김치찌개", "confidence": 0.82}
    ]
  }
}
```

실패 응답 예시 (빈 파일 등, HTTP 400):

```json
{
  "success": false,
  "code": "COM_001",
  "msg": "이미지 파일이 비어 있습니다."
}
```

주요 실패 코드: `COM_001`, `AI_001`, `AI_003`

### 6) `POST /api/v1/ai/food-images/analyze`

- 용도: 음식 이미지에서 식재료 추정
- 요청 `Content-Type`: `multipart/form-data`
- 폼 필드:
  - `image`: 이미지 파일
  - `requestId`: 선택

요청 예시 (`curl`):

```bash
curl -sS -X POST "http://localhost:8000/api/v1/ai/food-images/analyze" \
  -H "Accept-Language: ko" \
  -F "image=@./sample-food.jpg" \
  -F "requestId=req-002"
```

성공 응답 예시:

```json
{
  "success": true,
  "data": {
    "requestId": "req-002",
    "foodName": "김치찌개",
    "ingredients": [
      {"ingredientCode": "SOYBEAN", "confidence": 0.9},
      {"ingredientCode": "WHEAT", "confidence": 0.75}
    ],
    "notes": "추정 결과이며 실제와 다를 수 있습니다."
  }
}
```

실패 응답 예시 (빈 파일 등, HTTP 400):

```json
{
  "success": false,
  "code": "COM_001",
  "msg": "이미지 파일이 비어 있습니다."
}
```

주요 실패 코드: `COM_001`, `AI_001`, `AI_003`

### 공통 헤더

- `Accept-Language`: `ko`, `en`, `zh-CN`, `vi`, `ja` (예: `en-US` 허용)

레거시 호환 API:

- `GET /health`
- `POST /crawl-and-forward`
- `POST /identify-image-and-forward`
- `POST /analyze-food-text-and-forward`
- `POST /analyze-image-and-forward`

## Swagger 사용 방법

### 1) Swagger UI 접속

```bash
python3 -m uvicorn user_features.live_service:app --host 0.0.0.0 --port 8000
open http://localhost:8000/docs
```

### 2) OpenAPI JSON 확인

```bash
curl http://localhost:8000/openapi.json
```

`/api/v1` JSON 엔드포인트에는 **요청 본문 예시**가 등록되어 있고, 각 작업의 **응답(200·400·500 등) 예시**도 OpenAPI에 포함되어 있습니다. Swagger UI에서 `Try it out` 시 본문 드롭다운으로 예시를 고를 수 있으며, 응답 섹션에서 상태 코드별 예시를 확인할 수 있습니다.

### 3) 엔드포인트 테스트 절차

1. `/docs` 접속 후 테스트할 API 선택
2. `Try it out` 클릭
3. 요청 파라미터/Body 입력
4. `Execute` 클릭
5. Response Body/Code 확인

### 4) 인증이 필요한 레거시 API 테스트

- `POST /crawl-and-forward`는 `SPRING_API_TOKEN`이 설정된 경우 Bearer 토큰 필요
- Swagger 우측 상단 `Authorize`에서 `Bearer <token>` 형태로 입력

## CLI 실행 (scripts)

```bash
python3 scripts/crawl_menus.py
python3 scripts/push_menus.py --dry-run --indent 2
python3 scripts/push_extended.py --dry-run
python3 scripts/i18n_summary.py --csv menu_allergy_gemini.csv --locale en
python3 scripts/allergy_filter.py --csv menu_allergy_gemini.csv --allergens "난류,우유" --json
```

## Spring 전송 Payload

주간 메뉴 통합 전송(`SPRING_MENUS_URL`)은 Swagger 래핑 형식을 사용합니다.

```json
{
  "success": true,
  "data": {
    "source": "https://www.kumoh.ac.kr",
    "capturedAt": "2026-04-07T03:00:00+00:00",
    "restaurants": []
  }
}
```

## 테스트

```bash
python3 -m pytest -q tests/live
```

### API 회귀 테스트 (자동, 내부 연동 최소 API 기준)

```bash
python3 scripts/smoke_api_regression.py
```

- 서버를 자동으로 기동/종료하면서 내부 연동용 최소 API를 점검합니다.
- 기본 실행 포트는 `8010`이며, 실행 중인 로컬 개발 서버(`8000`)와 충돌하지 않도록 설계되어 있습니다.
- 이미 서버가 떠 있다면 아래처럼 실행합니다.

```bash
python3 scripts/smoke_api_regression.py --use-existing-server --port 8000
```

### Postman 컬렉션(내부 연동 최소 API)

- 경로: `docs/postman/ai-agent-crawler-regression.postman_collection.json`
- 변수:
  - `baseUrl` (기본값: `http://127.0.0.1:8000`)
- 포함 항목:
  - health 체크
  - 식단 크롤링/분석/번역 엔드포인트
  - OpenAPI에서 `spring-compat` 비노출 확인

## 운영 참고

- `ENABLE_DIRECT_IMAGE_ANALYSIS=true`일 때만 직접 이미지 상세분석 API 사용
- `CRAWL_SOURCE_ALLOWLIST`로 크롤링 source host 제한 가능
- Gemini 호출량에 맞춰 `WEEKLY_MENU_BATCH_SIZE`, `WEEKLY_MENU_SLEEP_SECONDS` 조정 권장

