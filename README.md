# AI-Agent-Crawler

금오공과대학교 급식 페이지 등 **외부 소스에서 식단을 크롤링**하고, **Google Gemini**로 메뉴 분석·번역·이미지 추론을 수행합니다. **Spring Boot**와는 두 가지 방식으로 붙을 수 있습니다.

1. **Spring → Python** — 백엔드가 `RestClient`로 이 서비스의 **비래핑** API를 호출 (`MealCrawlProperties` 기본 경로와 동일).
2. **Python → Spring (레거시)** — 주간 크롤·이미지/텍스트 분석 후 Spring 수집 URL로 HTTP POST (`SPRING_*_URL`).

---

## 요구 사항

- **Python 3.10+** 권장 (의존성 일부는 3.9에서 경고가 날 수 있음).
- 크롤·Gemini 호출 시 **인터넷** 접근.
- AI 기능(분석·번역·이미지)에는 **`GEMINI_API_KEY`** 필요.

---

## 빠른 시작

```bash
pip install -r requirements.txt
cp .env.example .env
# .env 에 GEMINI_API_KEY 등 필요한 값 설정
```

서버 기동(권장 진입점):

```bash
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

동일 앱 인스턴스:

```bash
python3 -m uvicorn user_features.live_service:app --host 0.0.0.0 --port 8000
```

확인:

```bash
curl -sS http://127.0.0.1:8000/health
```

API 문서: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) · OpenAPI JSON: `/openapi.json`

---

## 저장소 구조

| 경로 | 역할 |
|------|------|
| `main.py` | Uvicorn 진입점 (`uvicorn main:app`). `user_features.live_service.app` 와 동일 인스턴스. |
| `user_features/live_service.py` | `.env` 로드 후 `create_app(load_runtime_context())` 조립. |
| `app/config` | `runtime`(환경변수·`ServiceConfig`), `app_factory`(FastAPI·라우터·주간 태스크). |
| `app/api/routes` | `live`(레거시 + `/api/v1` 래핑), `spring_native`(비래핑 Spring 연동). |
| `app/schemas` | Pydantic 모델·OpenAPI 예시 연계. |
| `app/services` | `live_service`, `ops` 등 유스케이스. |
| `app/repositories` | Spring HTTP, 크롤 등 외부 I/O. |
| `app/domain` | 크롤러·이미지·알레르기 도메인 로직. |
| `app/common` | 공통 유틸. |
| `scripts` | 스모크·검증·배치용 CLI. |
| `tests` | `pytest` — `live`, `integration` 등. |
| `docs/postman` | 회귀용 Postman 컬렉션. |

`spring_compat` 스텁 레이어는 제거되었습니다. Spring과의 **공식 HTTP 계약**은 아래 **Spring-native** 경로와 **OpenAPI 래핑** 경로 두 축으로 정리되어 있습니다.

---

## API 축 요약

모든 `/api/v1/*` JSON API는 가능하면 **`Accept-Language`** 헤더를 보냅니다. 허용 예: `ko`, `en`, `zh-CN`, `vi`, `ja` (`en-US` 형태도 허용).

### 1) Spring-native (비래핑) — `PythonMealClientAdapter` / `MealCrawlProperties` 기본값과 정렬

| 메서드 | 경로 | 성공 시 본문 |
|--------|------|----------------|
| `POST` | `/api/v1/crawl/meals` | `schoolName`, `cafeteriaName`, `sourceUrl`, `startDate`, `endDate`, `meals` **직접** ( `success` / `data` 없음 ) |
| `POST` | `/api/v1/menus/analyze` | `{ "results": [...] }` |
| `POST` | `/api/v1/menus/translate` | `{ "results": [...] }` |

**오류 시** HTTP 상태 코드와 함께 **`{"message": "..."}`** 형태(JSON). 크롤 조건 오류는 주로 `400`, 외부 소스 실패는 `502`, Gemini 미설정 등은 `500` 등으로 구분됩니다.

### 2) OpenAPI 래핑 (`/api/v1/python/...` 및 기타)

| 메서드 | 경로 | 응답 형식 |
|--------|------|-----------|
| `POST` | `/api/v1/python/meals/crawl` | `success` + `data` |
| `POST` | `/api/v1/python/menus/analyze` | 동일 |
| `POST` | `/api/v1/python/menus/translate` | 동일 |
| `POST` | `/api/v1/translations` | 자유 문장 번역 |
| `POST` | `/api/v1/ai/menu-board/analyze` | `multipart/form-data` (`image`, 선택 `requestId`) |
| `POST` | `/api/v1/ai/food-images/analyze` | 동일 |

**성공**

```json
{ "success": true, "data": { } }
```

**실패**

```json
{ "success": false, "code": "PYM_400", "msg": "..." }
```

래핑 API에서 자주 쓰이는 코드: `COM_001`(이미지 등 검증), `COM_002`(요청 스키마/검증), `PYM_400`, `PYM_502`, `AI_001`(Gemini 키 미설정 등). 세부 `msg`·HTTP 상태는 응답 본문과 `/docs` 예시를 따릅니다.

### 3) 레거시(루트) — 운영·전달용

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/health` | 설정 요약(`weeklyCrawlConfigured` 등). |
| `POST` | `/crawl-and-forward` | 주간 식단 크롤 후 `SPRING_MENUS_URL` 로 전달. `SPRING_API_TOKEN` 설정 시 **Bearer 토큰** 필요. |
| `POST` | `/identify-image-and-forward` | 이미지 → 음식명 식별 → `SPRING_IMAGE_IDENTIFY_URL`. |
| `POST` | `/analyze-food-text-and-forward` | 텍스트 분석 → `SPRING_TEXT_ANALYSIS_URL`. |
| `POST` | `/analyze-image-and-forward` | 상세 이미지 분석 → `SPRING_IMAGE_ANALYSIS_URL`. **`ENABLE_DIRECT_IMAGE_ANALYSIS=true`** 일 때만. |

---

## Spring Boot와 연동할 때

### Spring이 Python을 호출하는 경우

백엔드(예: `mealguide`)에서 **`MEAL_CRAWL_PYTHON_BASE_URL`** 등으로 이 서비스 베이스 URL을 지정하고, **`/api/v1/crawl/meals`** 등 비래핑 경로로 호출합니다. 로컬 검증 시 스케줄러/수동 트리거로 `PythonMealClientAdapter` 가 실제 요청을 보내는지 로그·브레이크포인트로 확인합니다.

### Python이 Spring을 호출하는 경우

`.env` 에 **`SPRING_MENUS_URL`**, **`SPRING_IMAGE_*`**, **`SPRING_TEXT_ANALYSIS_URL`** 등을 맞춘 뒤, **`POST /crawl-and-forward`** 등 레거시 엔드포인트를 호출해 Spring 쪽 로그·DB 변화를 확인합니다.

### JVM 없이 HTTP 계약만 검증

```bash
python3 scripts/verify_spring_python_integration.py
# 고정 포트가 필요하면: python3 scripts/verify_spring_python_integration.py --port 8890
```

- 기본은 **`--port 0`**(미지정과 동일)으로 **빈 포트를 자동 선택**해 Uvicorn을 띄웁니다.
- `RestClient` 와 동일한 방식으로 **`POST /api/v1/crawl/meals`** 를 호출해 비래핑 응답을 검사합니다.
- 로컬 모의 HTTP 서버로 **`SpringRepository.post_json`** 전달 경로를 검사합니다.

**포함하지 않는 것:** 실제 Spring Boot + DB + Redis 전체 E2E. 백엔드 쪽 어댑터 단위 테스트 예:

```bash
cd ../Backend && bash ./mvnw test -Dtest=PythonMealClientAdapterTest
```

---

## 환경 변수

**한 줄 요약:** 저장소에 적힌 변수를 **전부 넣을 필요는 없습니다.** `app/config/runtime.py` 기준으로, **빈 값이면 `None` 또는 코드에 박힌 기본값**이 적용되고, 서버는 대개 기동됩니다. 다만 값이 **형식에 맞지 않으면** 기동 시 `RuntimeError` 로 바로 종료됩니다(예: `WEEKLY_CRAWL_DAY=xyz`, `SERVICE_TIMEZONE=Invalid/Zone`).

아래 표의 **필수**는 「그 기능을 쓰려면 반드시」라는 뜻이며, 전역 필수는 **`GEMINI_API_KEY`도 아님**입니다(없으면 크롤만 되고 AI·번역·이미지 API는 실패).

### 전체 목록 (이름 · 기본값 · 용도)

| 변수 | 기본값 | 그 기능을 쓰려면 |
|------|--------|------------------|
| `GEMINI_API_KEY` | 없음 → Gemini 클라이언트 미생성 | **메뉴 분석·번역·이미지 AI·주간 크롤(`run_weekly_crawl_once`)** 에 필요 |
| `GEMINI_MODEL` | `gemini-2.5-flash` | 선택. `/api/v1/python/menus/*`, 이미지 분석 등 **HTTP 라우트**에서 쓰는 모델 |
| `WEEKLY_MENU_MODEL` | `gemini-2.5-flash-lite` | 선택. **주간 배치 크롤**(`crawl-and-forward`, 백그라운드 루프) 안 Gemini 분석에 사용 |
| `SPRING_MENUS_URL` | 없음 | **`POST /crawl-and-forward`**, 백그라운드 주간 전달, `/health` 의 `weeklyCrawlConfigured` |
| `SPRING_IMAGE_ANALYSIS_URL` | 없음 | **`POST /analyze-image-and-forward`** |
| `SPRING_IMAGE_IDENTIFY_URL` | 없음 | **`POST /identify-image-and-forward`** |
| `SPRING_TEXT_ANALYSIS_URL` | 없음 | **`POST /analyze-food-text-and-forward`** |
| `SPRING_API_TOKEN` | 없음 | 설정 시 **`POST /crawl-and-forward`** 만 들어오는 요청에 `Authorization: Bearer …` 강제 |
| `SPRING_API_KEY` | 없음 | 선택. Spring 수집 API가 **X-API-Key** 를 요구할 때 전송 헤더에 붙음 |
| `WEEKLY_CRAWL_DAY` | `mon` | `mon`…`sun` 만 허용 |
| `WEEKLY_CRAWL_HOUR` | `6` | `0`–`23` |
| `WEEKLY_CRAWL_MINUTE` | `0` | `0`–`59` |
| `SERVICE_TIMEZONE` | `Asia/Seoul` | IANA 이름. 잘못된 이름이면 **기동 실패** |
| `WEEKLY_MENU_BATCH_SIZE` | `4` | 정수 ≥ 1 |
| `WEEKLY_MENU_SLEEP_SECONDS` | `21.0` | 실수 ≥ 0 (배치 사이 대기) |
| `I18N_LOCALE` | `en` | 주간 페이로드 요약 로케일 |
| `ENABLE_DIRECT_IMAGE_ANALYSIS` | `false` | `true` 일 때만 **`/analyze-image-and-forward`** 허용 |
| `AI_MAX_CONCURRENT_TASKS` | `4` | 정수 ≥ 1. **`/api/v1/python/menus/*` 와 Spring-native `/api/v1/menus/*`** 메뉴 분석·번역 동시성 |
| `CRAWL_SOURCE_ALLOWLIST` | 없음(제한 없음) | 쉼표 구분 호스트. **설정 시** 해당 호스트만 크롤 허용 (`app/services/ops.py`) |

**`POST /api/v1/crawl/meals` 등 Spring-native 크롤**은 외부 급식 페이지만 보면 되므로 **`GEMINI_API_KEY` 없이도** 동작할 수 있습니다(금오 URL 등). 반면 **`/api/v1/menus/analyze`**, **`translate`**, **`/api/v1/python/...` AI 계열**, **주간 `crawl-and-forward`** 는 키가 필요합니다.

### 시나리오별 `.env` 예시

**1) 로컬에서 크롤 API만 검증 (Spring 없음, Gemini 없음)**

```env
# 비워 두거나 최소만
# 외부 URL 크롤만 할 때는 키 없이도 /api/v1/crawl/meals 등 호출 가능할 수 있음
```

**2) Spring이 Python을 호출하는 전형 (백엔드에만 URL 설정, Python은 Gemini까지 씀)**

```env
GEMINI_API_KEY=AIza...your-key...
GEMINI_MODEL=gemini-2.5-flash
```

**3) Python이 Spring으로 주간 식단까지 밀어 넣기**

```env
GEMINI_API_KEY=AIza...
SPRING_MENUS_URL=http://localhost:8080/api/menus/ingest
# Spring 이 Bearer 를 요구하면:
# SPRING_API_TOKEN=my-shared-secret
# Spring 이 API Key 를 요구하면:
# SPRING_API_KEY=ingest-key-123
WEEKLY_MENU_MODEL=gemini-2.5-flash-lite
WEEKLY_MENU_BATCH_SIZE=4
WEEKLY_MENU_SLEEP_SECONDS=21.0
I18N_LOCALE=en
WEEKLY_CRAWL_DAY=mon
WEEKLY_CRAWL_HOUR=6
WEEKLY_CRAWL_MINUTE=0
SERVICE_TIMEZONE=Asia/Seoul
```

**4) 레거시 “분석 후 Spring 전달” 엔드포인트까지**

```env
GEMINI_API_KEY=AIza...
SPRING_MENUS_URL=http://localhost:8080/api/menus/ingest
SPRING_IMAGE_IDENTIFY_URL=http://localhost:8080/api/image-identify/ingest
SPRING_TEXT_ANALYSIS_URL=http://localhost:8080/api/food-analysis/ingest
SPRING_IMAGE_ANALYSIS_URL=http://localhost:8080/api/image-analysis/ingest
ENABLE_DIRECT_IMAGE_ANALYSIS=true
SPRING_API_TOKEN=my-shared-secret
```

**5) 운영에서 크롤 대상 호스트만 제한**

```env
CRAWL_SOURCE_ALLOWLIST=www.kumoh.ac.kr,kumoh.ac.kr
```

**6) AI 호출 동시성만 조정**

```env
GEMINI_API_KEY=AIza...
AI_MAX_CONCURRENT_TASKS=2
```

원본 한 줄짜리 주석 템플릿은 **`/.env.example`** 에 그대로 두었습니다. 변수 추가·이름 변경 시 **`app/config/runtime.py`** 와 이 README를 같이 맞추면 됩니다.

---

## 백그라운드 주간 크롤

`app/config/app_factory.py` 의 **lifespan** 에서 비동기 태스크가 돌며, 설정된 요일·시각에 **`run_weekly_crawl_once`** 를 호출합니다. `SPRING_MENUS_URL` 이 비어 있으면 호출마다 예외가 나고 로그에 `weekly crawl forwarding failed` 가 남습니다. 주간 전달을 쓰려면 URL·`GEMINI_API_KEY` 를 맞추거나, 로컬 개발 시에는 백그라운드 루프를 감안해 `.env` 를 구성하세요. 설정 여부는 **`GET /health`** 의 `weeklyCrawlConfigured` 로 확인합니다.

---

## API 레퍼런스: 호출 예시와 응답

아래 예시의 베이스 URL은 **`http://127.0.0.1:8000`** 입니다. JSON API에는 가능하면 **`Accept-Language: ko`** (또는 `en`, `zh-CN`, `vi`, `ja`)를 붙입니다.

---

### `GET /health`

**호출**

```bash
curl -sS "http://127.0.0.1:8000/health"
```

**응답 200**

```json
{
  "ok": true,
  "weeklyCrawlConfigured": true,
  "imageAnalysisConfigured": false,
  "imageIdentifyConfigured": false,
  "textAnalysisConfigured": false,
  "directImageAnalysisEnabled": false,
  "timezone": "Asia/Seoul"
}
```

`weeklyCrawlConfigured` 등은 `.env` 의 `SPRING_*_URL` 설정 여부에 따라 달라집니다.

---

### `POST /crawl-and-forward`

주간 식단 크롤·Gemini 분석 후 **`SPRING_MENUS_URL`** 로 전송합니다. `SPRING_API_TOKEN` 이 설정되어 있으면 **Bearer** 가 필요합니다.

**호출 (토큰 사용 시)**

```bash
curl -sS -X POST "http://127.0.0.1:8000/crawl-and-forward" \
  -H "Authorization: Bearer YOUR_SPRING_API_TOKEN"
```

**응답 200** (전송·크롤 성공 시; `restaurants`·`analysisRows` 는 실제 페이로드에 따라 변동)

```json
{
  "status": "ok",
  "restaurants": 1,
  "analysisRows": 120,
  "i18nLocale": "en"
}
```

**응답 401** (`SPRING_API_TOKEN` 불일치·누락)

```json
{ "detail": "Unauthorized" }
```

**응답 500** (내부 예외; 메시지는 서버 로그에 상세)

```json
{ "detail": "Internal Server Error" }
```

`SPRING_MENUS_URL` 미설정·크롤 결과 없음·Spring HTTP 실패 등도 500 으로 이어질 수 있습니다.

---

### `POST /identify-image-and-forward`

**요청:** `multipart/form-data` — 필드 `image`(파일), 선택 **`request_id`**.

**호출**

```bash
curl -sS -X POST "http://127.0.0.1:8000/identify-image-and-forward" \
  -F "image=@./sample-food.jpg" \
  -F "request_id=req-001"
```

**응답 200** (`identified` 내용은 모델 출력 예시)

```json
{
  "status": "ok",
  "forwardStatus": 200,
  "identified": {
    "foodNameKo": "김치찌개",
    "confidence": 0.91
  }
}
```

**응답 500** (`SPRING_IMAGE_IDENTIFY_URL` 미설정 / `GEMINI_API_KEY` 미설정 등)

```json
{ "detail": "SPRING_IMAGE_IDENTIFY_URL is not set" }
```

**응답 502** (Spring 이 2xx 가 아닐 때)

```json
{ "detail": "Spring 응답 오류 HTTP 502" }
```

(실제 `detail` 문자열에 상태코드·본문 일부가 포함될 수 있습니다.)

---

### `POST /analyze-food-text-and-forward`

**요청:** `application/json` — 필드명 **`food_name`**

**호출**

```bash
curl -sS -X POST "http://127.0.0.1:8000/analyze-food-text-and-forward" \
  -H "Content-Type: application/json" \
  -d '{"food_name": "김치찌개"}'
```

**응답 200** (`analysis` 는 Gemini JSON 스키마 예시)

```json
{
  "status": "ok",
  "forwardStatus": 200,
  "analysis": {
    "foodNameKo": "김치찌개",
    "ingredientsKo": ["배추", "돼지고기"],
    "allergensKo": [{ "name": "밀", "reason": "부침가루 가능성" }]
  }
}
```

**응답 500** (`SPRING_TEXT_ANALYSIS_URL` 미설정)

```json
{ "detail": "SPRING_TEXT_ANALYSIS_URL is not set" }
```

---

### `POST /analyze-image-and-forward`

**조건:** `ENABLE_DIRECT_IMAGE_ANALYSIS=true` 이고 `SPRING_IMAGE_ANALYSIS_URL`·`GEMINI_API_KEY` 필요.

**호출**

```bash
curl -sS -X POST "http://127.0.0.1:8000/analyze-image-and-forward" \
  -F "image=@./sample-food.jpg" \
  -F "user_id=u-1" \
  -F "request_id=req-002"
```

**응답 200** (`analysis` 구조는 이미지 분석 파이프라인 결과에 따름)

```json
{
  "status": "ok",
  "forwardStatus": 200,
  "analysis": {
    "음식명": "김치찌개",
    "추정_식재료": [{ "재료": "대두", "신뢰도": 0.88 }],
    "주의사항": "추정 결과이며 실제와 다를 수 있습니다."
  }
}
```

**응답 403** (직접 이미지 분석 비활성)

```json
{ "detail": "Direct image analysis is disabled." }
```

---

### `POST /api/v1/crawl/meals` (Spring-native, 비래핑)

**호출**

```bash
curl -sS -X POST "http://127.0.0.1:8000/api/v1/crawl/meals" \
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

**응답 200**

```json
{
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
        { "cornerName": "학생식당", "displayOrder": 1, "menuName": "김치찌개" },
        { "cornerName": "학생식당", "displayOrder": 2, "menuName": "된장찌개" }
      ]
    }
  ]
}
```

**응답 400** (식당·URL 조건 불가)

```json
{ "message": "요청 식단 조회 조건이 유효하지 않거나 데이터가 없습니다." }
```

**응답 502** (외부 크롤 소스 실패)

```json
{ "message": "외부 크롤링 소스 조회에 실패했습니다. 잠시 후 다시 시도해주세요." }
```

**응답 400** (`Accept-Language` 허용 목록 위반 등; `message` 에 전체 설명 문자열)

```json
{ "message": "지원하지 않는 Accept-Language: fr. 허용: ko, en, zh-CN, vi, ja" }
```

---

### `POST /api/v1/menus/analyze` (Spring-native)

**호출**

```bash
curl -sS -X POST "http://127.0.0.1:8000/api/v1/menus/analyze" \
  -H "Content-Type: application/json" \
  -H "Accept-Language: ko" \
  -d '{"menus":[{"menuId":101,"menuName":"김치찌개"}]}'
```

**응답 200**

```json
{
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
        { "ingredientCode": "SOYBEAN", "confidence": 0.88 },
        { "ingredientCode": "WHEAT", "confidence": 0.81 }
      ]
    }
  ]
}
```

**응답 500** (`GEMINI_API_KEY` 없음)

```json
{ "message": "GEMINI_API_KEY is not set" }
```

---

### `POST /api/v1/menus/translate` (Spring-native)

**호출**

```bash
curl -sS -X POST "http://127.0.0.1:8000/api/v1/menus/translate" \
  -H "Content-Type: application/json" \
  -H "Accept-Language: ko" \
  -d '{"menus":[{"menuId":101,"menuName":"김치찌개"}],"targetLanguages":["en","ja"]}'
```

**응답 200**

```json
{
  "results": [
    {
      "menuId": 101,
      "sourceName": "김치찌개",
      "translations": [
        { "langCode": "en", "translatedName": "Kimchi stew" },
        { "langCode": "ja", "translatedName": "キムチチゲ" }
      ],
      "translationErrors": []
    }
  ]
}
```

**응답 500** (`GEMINI_API_KEY` 없음)

```json
{ "message": "GEMINI_API_KEY is not set" }
```

---

### `POST /api/v1/python/meals/crawl` (래핑)

요청 본문은 Spring-native 크롤과 **동일 스키마**입니다.

**호출**

```bash
curl -sS -X POST "http://127.0.0.1:8000/api/v1/python/meals/crawl" \
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

**응답 200**

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
          { "cornerName": "학생식당", "displayOrder": 1, "menuName": "김치찌개" },
          { "cornerName": "학생식당", "displayOrder": 2, "menuName": "된장찌개" }
        ]
      }
    ]
  }
}
```

**응답 400** (조건 불가)

```json
{
  "success": false,
  "code": "PYM_400",
  "msg": "요청 식단 조회 조건이 유효하지 않거나 데이터가 없습니다."
}
```

**응답 502** (업스트림 실패)

```json
{
  "success": false,
  "code": "PYM_502",
  "msg": "외부 크롤링 소스 조회에 실패했습니다. 잠시 후 다시 시도해주세요."
}
```

**응답 400** (JSON 스키마 위반 등)

```json
{
  "success": false,
  "code": "COM_002",
  "msg": "요청 데이터 변환 과정에서 오류가 발생했습니다."
}
```

---

### `POST /api/v1/python/menus/analyze` (래핑)

**호출**

```bash
curl -sS -X POST "http://127.0.0.1:8000/api/v1/python/menus/analyze" \
  -H "Content-Type: application/json" \
  -H "Accept-Language: ko" \
  -d '{"menus":[{"menuId":101,"menuName":"김치찌개"}]}'
```

**응답 200**

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
          { "ingredientCode": "SOYBEAN", "confidence": 0.88 },
          { "ingredientCode": "WHEAT", "confidence": 0.81 }
        ]
      }
    ]
  }
}
```

**응답 500**

```json
{
  "success": false,
  "code": "AI_001",
  "msg": "GEMINI_API_KEY is not set"
}
```

---

### `POST /api/v1/python/menus/translate` (래핑)

**호출**

```bash
curl -sS -X POST "http://127.0.0.1:8000/api/v1/python/menus/translate" \
  -H "Content-Type: application/json" \
  -H "Accept-Language: ko" \
  -d '{"menus":[{"menuId":101,"menuName":"김치찌개"}],"targetLanguages":["en","ja"]}'
```

**응답 200**

```json
{
  "success": true,
  "data": {
    "results": [
      {
        "menuId": 101,
        "sourceName": "김치찌개",
        "translations": [
          { "langCode": "en", "translatedName": "Kimchi stew" },
          { "langCode": "ja", "translatedName": "キムチチゲ" }
        ],
        "translationErrors": []
      }
    ]
  }
}
```

**응답 500**

```json
{
  "success": false,
  "code": "AI_001",
  "msg": "GEMINI_API_KEY is not set"
}
```

---

### `POST /api/v1/translations` (래핑)

**호출**

```bash
curl -sS -X POST "http://127.0.0.1:8000/api/v1/translations" \
  -H "Content-Type: application/json" \
  -H "Accept-Language: ko" \
  -d '{"sourceLang":"ko","targetLang":"en","text":"이 음식에 밀가루가 들어가나요?"}'
```

**응답 200**

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

**응답 500** (`GEMINI_API_KEY` 없음)

```json
{
  "success": false,
  "code": "AI_001",
  "msg": "GEMINI_API_KEY is not set"
}
```

---

### `POST /api/v1/ai/menu-board/analyze` (래핑, multipart)

**호출**

```bash
curl -sS -X POST "http://127.0.0.1:8000/api/v1/ai/menu-board/analyze" \
  -H "Accept-Language: ko" \
  -F "image=@./sample-menu-board.jpg" \
  -F "requestId=req-001"
```

**응답 200**

```json
{
  "success": true,
  "data": {
    "requestId": "req-001",
    "recognizedMenus": [{ "menuName": "김치찌개", "confidence": 0.82 }]
  }
}
```

**응답 400** (빈 파일)

```json
{
  "success": false,
  "code": "COM_001",
  "msg": "이미지 파일이 비어 있습니다."
}
```

**응답 500**

```json
{
  "success": false,
  "code": "AI_001",
  "msg": "GEMINI_API_KEY is not set"
}
```

---

### `POST /api/v1/ai/food-images/analyze` (래핑, multipart)

**호출**

```bash
curl -sS -X POST "http://127.0.0.1:8000/api/v1/ai/food-images/analyze" \
  -H "Accept-Language: ko" \
  -F "image=@./sample-food.jpg" \
  -F "requestId=req-002"
```

**응답 200** (`ingredients` 는 모델·매핑 결과에 따라 변동)

```json
{
  "success": true,
  "data": {
    "requestId": "req-002",
    "foodName": "김치찌개",
    "ingredients": [
      { "ingredientCode": "SOYBEAN", "confidence": 0.9 },
      { "ingredientCode": "WHEAT", "confidence": 0.75 }
    ],
    "notes": "추정 결과이며 실제와 다를 수 있습니다."
  }
}
```

**응답 400** (빈 파일)

```json
{
  "success": false,
  "code": "COM_001",
  "msg": "이미지 파일이 비어 있습니다."
}
```

**응답 413** (10MB 초과 시, 메시지 예시)

```json
{
  "success": false,
  "code": "COM_001",
  "msg": "이미지 파일이 너무 큽니다 (최대 10MB)."
}
```

---

## Swagger UI

1. 서버 기동 후 `/docs` 접속.
2. 엔드포인트 선택 → **Try it out** → 본문 예시 선택(등록된 경우) → **Execute**.
3. `/crawl-and-forward` 는 `SPRING_API_TOKEN` 이 있으면 우측 **Authorize** 에 `Bearer <token>` 입력.

---

## CLI (`scripts/`)

| 스크립트 | 설명 |
|----------|------|
| `smoke_api_regression.py` | 서버 자동 기동(기본 포트 `8010`) 또는 `--use-existing-server` 로 최소 API 회귀. |
| `verify_spring_python_integration.py` | Spring↔Python HTTP 계약 스모크(위 참고). |
| `crawl_menus.py` | 메뉴 크롤 CLI. |
| `push_menus.py` / `push_extended.py` | Spring 쪽으로 푸시(드라이런 옵션 등). |
| `i18n_summary.py` / `allergy_filter.py` | CSV·알레르기 보조. |

예:

```bash
python3 scripts/smoke_api_regression.py
python3 scripts/push_menus.py --dry-run --indent 2
```

---

## 테스트

```bash
python3 -m pytest -q tests/live
python3 -m pytest -q tests/integration
```

- `tests/integration/test_spring_native_contract.py` — 비래핑 경로 계약.
- `tests/integration/test_ai_agent_api.py` — `GEMINI_API_KEY` 없으면 skip, 있으면 실 API.

Postman: `docs/postman/ai-agent-crawler-regression.postman_collection.json` (`baseUrl` 변수 기본 `http://127.0.0.1:8000`).

---

## Spring 으로 넘기는 주간 페이로드(개념)

`SPRING_MENUS_URL` 로 보내는 본문은 앱 내부에서 가공된 **성공 래핑 형태** 등 레거시 스키마를 따릅니다. 정확한 필드는 `LiveService`·레포지토리 구현과 Spring 수집 API 스펙을 함께 보세요. (OpenAPI 문서의 `/api/v1/python/meals/crawl` 응답 `data` 와 혼동하지 마세요.)

---

## 운영 시 참고

- Gemini 호출량에 맞춰 **`WEEKLY_MENU_BATCH_SIZE`**, **`WEEKLY_MENU_SLEEP_SECONDS`** 조정.
- 외부 크롤 남용 방지·보안을 위해 **`CRAWL_SOURCE_ALLOWLIST`** 사용을 검토.
- 이미지 업로드는 **최대 10MB**, 허용 MIME: JPEG / PNG / WebP / GIF (`app/config/runtime.py`).
