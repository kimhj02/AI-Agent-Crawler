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

자주 쓰이는 코드 예: `COM_001`, `COM_002`, `PYM_400`, `PYM_502`, `AI_001`, `AI_002`, `AI_003`. 세부 메시지·HTTP 코드는 OpenAPI `/docs` 의 응답 예시를 기준으로 합니다.

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
```

- `RestClient` 와 동일한 방식으로 **`POST /api/v1/crawl/meals`** 를 호출해 비래핑 응답을 검사합니다.
- 로컬 모의 HTTP 서버로 **`SpringRepository.post_json`** 전달 경로를 검사합니다.

**포함하지 않는 것:** 실제 Spring Boot + DB + Redis 전체 E2E. 백엔드 쪽 어댑터 단위 테스트 예:

```bash
cd ../Backend && bash ./mvnw test -Dtest=PythonMealClientAdapterTest
```

---

## 환경 변수

상세 주석은 **`.env.example`** 을 기준으로 하세요. 요약:

| 변수 | 용도 |
|------|------|
| `GEMINI_API_KEY` | Gemini 클라이언트. 없으면 AI·번역 관련 API는 실패하거나 비활성. |
| `GEMINI_MODEL` | 기본 `gemini-2.5-flash` 등 덮어쓰기. |
| `SPRING_MENUS_URL` | 주간 크롤 결과 전달 URL. 없으면 `/health` 의 `weeklyCrawlConfigured` 가 false. |
| `SPRING_IMAGE_ANALYSIS_URL` | 이미지 상세 분석 전달. |
| `SPRING_IMAGE_IDENTIFY_URL` | 이미지 음식명 식별 전달. |
| `SPRING_TEXT_ANALYSIS_URL` | 텍스트 음식 분석 전달. |
| `SPRING_API_TOKEN` | 설정 시 `/crawl-and-forward` 등에 Bearer 로 검증. |
| `SPRING_API_KEY` | 선택: Spring 이 X-API-Key 를 요구할 때. |
| `WEEKLY_CRAWL_DAY` / `HOUR` / `MINUTE` | 주간 루프 시각 (기본 월 06:00, `Asia/Seoul`). |
| `SERVICE_TIMEZONE` | 타임존 이름. |
| `WEEKLY_MENU_MODEL` / `WEEKLY_MENU_BATCH_SIZE` / `WEEKLY_MENU_SLEEP_SECONDS` | 주간 배치·슬립. |
| `I18N_LOCALE` | 주간 크롤 관련 로케일 기본. |
| `ENABLE_DIRECT_IMAGE_ANALYSIS` | `true` 일 때만 `/analyze-image-and-forward` 허용. |
| `AI_MAX_CONCURRENT_TASKS` | 메뉴 분석·번역 동시성 상한. |
| `CRAWL_SOURCE_ALLOWLIST` | 설정 시 크롤 허용 호스트 제한 (`app/services/ops.py`). |

---

## 백그라운드 주간 크롤

`app/config/app_factory.py` 의 **lifespan** 에서 비동기 태스크가 돌며, 설정된 요일·시각에 **`run_weekly_crawl_once`** 를 호출합니다. `SPRING_MENUS_URL` 이 비어 있으면 전달은 하지 않습니다(크롤 로직·설정은 `/health` 로 확인).

---

## 호출 예시

### Spring-native 크롤 (비래핑)

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

성공 시 루트에 `meals` 배열이 포함됩니다. 실패 시 예: `{"message":"외부 크롤링 소스 조회에 실패했습니다. 잠시 후 다시 시도해주세요."}` (HTTP 502).

### OpenAPI 래핑 크롤 (동일 요청 본문, 응답만 래핑)

```bash
curl -sS -X POST "http://127.0.0.1:8000/api/v1/python/meals/crawl" \
  -H "Content-Type: application/json" \
  -H "Accept-Language: ko" \
  -d '{ "schoolName": "금오공과대학교", "cafeteriaName": "학생식당", "sourceUrl": "https://www.kumoh.ac.kr/ko/restaurant01.do", "startDate": "2026-04-21", "endDate": "2026-04-27" }'
```

나머지 엔드포인트의 요청·응답 스키마·예시는 **`/docs`** 와 `app/schemas/openapi_examples.py` 를 참고하는 것이 가장 정확합니다.

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
