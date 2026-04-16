# AI-Agent-Crawler

Gemini API와 Python으로 금오공대 급식표를 수집·분석합니다.

## 프로젝트 구조

| 폴더 | 설명 |
|------|------|
| `crawler/` | 급식표 HTML 크롤링, Spring Boot 전송(`push_menus`) |
| `menu_allergy/` | 메뉴 문구 기반 재료·알레르기 추정 (Gemini) |
| `food_image/` | 음식 이미지 기반 식재료 추정 (Gemini Vision) |
| `user_features/` | 알레르기 필터, 다국어 요약, 확장 Spring 페이로드 |
| `user_features/live/` | live service 라우터/설정/서비스 로직 분리 모듈 |

## 빠른 시작

```bash
pip install -r requirements.txt
cp .env.example .env
```

`.env` 필수값:

```bash
GEMINI_API_KEY=...
SPRING_MENUS_URL=http://localhost:8080/api/menus/ingest
SPRING_IMAGE_IDENTIFY_URL=http://localhost:8080/api/image-identify/ingest
SPRING_TEXT_ANALYSIS_URL=http://localhost:8080/api/food-analysis/ingest
```

## 이 프로젝트가 하는 일

### A. 주간 배치 (자동)
- 특정 요일/시간에 급식표를 크롤링
- Gemini로 메뉴별 재료/알레르기 분석
- i18n(영문 등) 요약 생성
- Spring으로 통합 페이로드 전송 (`SPRING_MENUS_URL`)

### B. 실시간 이미지 2단계 플로우
1. Spring → Python 이미지 전달 (`/identify-image-and-forward`)
2. Python이 음식명만 식별 후 Spring 전송 (`SPRING_IMAGE_IDENTIFY_URL`)
3. Spring DB 조회 후, 정보 없으면 텍스트 음식명으로 상세 분석 요청 (`/analyze-food-text-and-forward`)
4. Python이 재료/알레르기 분석 후 Spring 전송 (`SPRING_TEXT_ANALYSIS_URL`)

### C. 직접 이미지 상세분석 (옵션)
- `/analyze-image-and-forward`
- 기본 비활성화 (`ENABLE_DIRECT_IMAGE_ANALYSIS=false`)
- 필요한 경우만 `true`로 활성화

## 로컬 실행

### 1) 상시 서비스 실행
```bash
python3 -m uvicorn user_features.live_service:app --host 0.0.0.0 --port 8000
```

### 2) 상태 확인
```bash
curl http://localhost:8000/health
```

### 3) Python API 명세 (`/api/v1`)

#### 3-1. 공통 규칙
- Base URL: `/api/v1`
- 공통 헤더
  - `Content-Type: application/json` (파일 업로드 API 제외)
  - `Accept-Language: ko | en | zh-CN | vi | ja` (locale 변형 허용: `en-US`, `ko-KR` 등)
- 성공 응답 형식
```json
{
  "success": true,
  "data": {
    "...": "..."
  }
}
```
- 실패 응답 형식
```json
{
  "success": false,
  "code": "COM_002",
  "msg": "요청 데이터 변환 과정에서 오류가 발생했습니다."
}
```

#### 3-2. API 목록

| 기능 | Method | Path | 비고 |
|------|--------|------|------|
| 날짜 구간 식단 크롤링 | `POST` | `/api/v1/python/meals/crawl` | 학교/식당/기간 기준 |
| 메뉴 상세 AI 분석 | `POST` | `/api/v1/python/menus/analyze` | `menuId` 상관관계 유지 |
| 메뉴 번역 | `POST` | `/api/v1/python/menus/translate` | `targetLanguages` 지원 |
| 자유 문장 번역 | `POST` | `/api/v1/translations` | source/target 언어 지정 |
| 메뉴판 이미지 분석 | `POST` | `/api/v1/ai/menu-board/analyze` | `multipart/form-data` |
| 음식 이미지 분석 | `POST` | `/api/v1/ai/food-images/analyze` | `multipart/form-data` |

#### 3-3. API별 요청/성공/실패 예시 (Notion 복붙용)

| API | 요청 타입 | 대표 성공 코드 | 대표 실패 코드 |
|-----|-----------|----------------|----------------|
| `POST /api/v1/python/meals/crawl` | `application/json` | `200` | `400`, `502`, `500` |
| `POST /api/v1/python/menus/analyze` | `application/json` | `200` | `400`, `500` |
| `POST /api/v1/python/menus/translate` | `application/json` | `200` | `400`, `500` |
| `POST /api/v1/translations` | `application/json` | `200` | `400`, `500` |
| `POST /api/v1/ai/menu-board/analyze` | `multipart/form-data` | `200` | `400`, `500` |
| `POST /api/v1/ai/food-images/analyze` | `multipart/form-data` | `200` | `400`, `500` |

##### A. `POST /api/v1/python/meals/crawl`

요청
```json
{
  "schoolName": "금오공과대학교",
  "cafeteriaName": "학생식당",
  "sourceUrl": "https://example.com/menu",
  "startDate": "2026-04-15",
  "endDate": "2026-04-21"
}
```

성공 (`200`)
```json
{
  "success": true,
  "data": {
    "schoolName": "금오공과대학교",
    "cafeteriaName": "학생식당",
    "sourceUrl": "https://example.com/menu",
    "startDate": "2026-04-15",
    "endDate": "2026-04-21",
    "meals": [
      {
        "mealDate": "2026-04-15",
        "mealType": "LUNCH",
        "menus": [
          {
            "cornerName": "한식",
            "displayOrder": 1,
            "menuName": "김치찌개"
          }
        ]
      }
    ]
  }
}
```

실패 (`400`)
```json
{
  "success": false,
  "code": "PYM_400",
  "msg": "요청 식단 조회 조건이 유효하지 않거나 데이터가 없습니다. (cafeteriaName=학생식당, sourceUrl=https://www.kumoh.ac.kr/ko/restaurant01.do, reason=...)"
}
```

##### B. `POST /api/v1/python/menus/analyze`

요청
```json
{
  "menus": [
    {
      "menuId": 101,
      "menuName": "김치찌개"
    }
  ]
}
```

성공 (`200`)
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
        "analyzedAt": "2026-04-08T12:30:00+09:00",
        "ingredients": [
          {
            "ingredientCode": "PORK",
            "confidence": 0.95
          },
          {
            "ingredientCode": "SOYBEAN",
            "confidence": 0.88
          }
        ]
      }
    ]
  }
}
```

실패 (`500`)
```json
{
  "success": false,
  "code": "AI_001",
  "msg": "GEMINI_API_KEY is not set"
}
```

##### C. `POST /api/v1/python/menus/translate`

요청
```json
{
  "menus": [
    {
      "menuId": 101,
      "menuName": "김치찌개"
    }
  ],
  "targetLanguages": ["en"]
}
```

성공 (`200`)
```json
{
  "success": true,
  "data": {
    "results": [
      {
        "menuId": 101,
        "sourceName": "김치찌개",
        "translations": [
          {
            "langCode": "en",
            "translatedName": "Kimchi stew"
          }
        ]
      }
    ]
  }
}
```

실패 (`400`)
```json
{
  "success": false,
  "code": "COM_002",
  "msg": "요청 데이터 변환 과정에서 오류가 발생했습니다."
}
```

##### D. `POST /api/v1/translations`

요청
```json
{
  "sourceLang": "ko",
  "targetLang": "en",
  "text": "이 음식에 밀가루가 들어가나요?"
}
```

성공 (`200`)
```json
{
  "success": true,
  "data": {
    "sourceLang": "ko",
    "targetLang": "en",
    "text": "이 음식에 밀가루가 들어가나요?",
    "translatedText": "Does this food contain wheat flour?"
  }
}
```

실패 (`500`)
```json
{
  "success": false,
  "code": "AI_002",
  "msg": "번역 실패: ..."
}
```

##### E. `POST /api/v1/ai/menu-board/analyze`

요청: `multipart/form-data`
- `image=<file>`
- `requestId=req-1` (optional)

성공 (`200`)
```json
{
  "success": true,
  "data": {
    "requestId": "req-1",
    "recognizedMenus": [
      {
        "menuName": "김치볶음밥",
        "confidence": 0.93
      }
    ]
  }
}
```

실패 (`500`)
```json
{
  "success": false,
  "code": "AI_003",
  "msg": "메뉴판 이미지 분석 실패: ..."
}
```

##### F. `POST /api/v1/ai/food-images/analyze`

요청: `multipart/form-data`
- `image=<file>`
- `requestId=req-2` (optional)

성공 (`200`)
```json
{
  "success": true,
  "data": {
    "requestId": "req-2",
    "foodName": "김치찌개",
    "ingredients": [
      {
        "ingredientCode": "PORK",
        "confidence": 0.92
      },
      {
        "ingredientCode": "SOYBEAN",
        "confidence": 0.81
      }
    ],
    "notes": "토핑은 각도에 따라 누락될 수 있습니다."
  }
}
```

실패 (`400`)
```json
{
  "success": false,
  "code": "COM_001",
  "msg": "이미지 파일이 너무 큽니다 (최대 10MB)."
}
```

#### 3-4. 에러 코드 표

| 코드 | 의미 |
|------|------|
| `COM_001` | 요청/헤더/파일 형식 등 일반 검증 오류 |
| `COM_002` | 요청 DTO 변환/검증 오류 |
| `AI_001` | AI 실행 불가 (예: `GEMINI_API_KEY` 누락) |
| `AI_002` | 번역 실패 |
| `AI_003` | 이미지 분석 실패 |
| `PYM_400` | 요청 식단 조회 조건 오류/데이터 미존재 |
| `PYM_502` | 외부 크롤링 소스 조회 실패(재시도 가능) |
| `PYM_500` | 식단 조회 중 예상치 못한 내부 오류 |

#### 3-5. 레거시/내부 포워딩 엔드포인트 (호환 유지)
- `GET /health`
- `POST /crawl-and-forward` (Bearer 인증: `SPRING_API_TOKEN` 설정 시 필수)
- `POST /identify-image-and-forward`
- `POST /analyze-food-text-and-forward`
- `POST /analyze-image-and-forward` (옵션, 기본 비활성화)

#### 3-6. Spring 스케줄러 연동 테스트용 `curl` 세트

아래 예시는 Python 서버가 `http://localhost:8000`에서 동작한다고 가정합니다.

사전 변수
```bash
PY_BASE="http://localhost:8000"
COMMON_HEADER_LANG="Accept-Language: ko"
```

1) 주간 식단 크롤링 (Spring 스케줄러 payload 기준)
```bash
curl -X POST "$PY_BASE/api/v1/python/meals/crawl" \
  -H "Content-Type: application/json" \
  -H "$COMMON_HEADER_LANG" \
  -d '{
    "schoolName":"금오공과대학교",
    "cafeteriaName":"학생식당",
    "sourceUrl":"https://www.kumoh.ac.kr/ko/restaurant01.do",
    "startDate":"2026-04-15",
    "endDate":"2026-04-21"
  }'
```

2) 신규 메뉴 AI 분석
```bash
curl -X POST "$PY_BASE/api/v1/python/menus/analyze" \
  -H "Content-Type: application/json" \
  -H "$COMMON_HEADER_LANG" \
  -d '{
    "menus":[
      {"menuId":101,"menuName":"김치찌개"},
      {"menuId":102,"menuName":"돈까스"}
    ]
  }'
```

3) 메뉴 번역 요청
```bash
curl -X POST "$PY_BASE/api/v1/python/menus/translate" \
  -H "Content-Type: application/json" \
  -H "$COMMON_HEADER_LANG" \
  -d '{
    "menus":[
      {"menuId":101,"menuName":"김치찌개"},
      {"menuId":102,"menuName":"돈까스"}
    ],
    "targetLanguages":["en"]
  }'
```

4) 자유 문장 번역
```bash
curl -X POST "$PY_BASE/api/v1/translations" \
  -H "Content-Type: application/json" \
  -H "$COMMON_HEADER_LANG" \
  -d '{
    "sourceLang":"ko",
    "targetLang":"en",
    "text":"이 음식에 밀가루가 들어가나요?"
  }'
```

5) 메뉴판 이미지 분석
```bash
curl -X POST "$PY_BASE/api/v1/ai/menu-board/analyze" \
  -H "$COMMON_HEADER_LANG" \
  -F "image=@/absolute/path/menu-board.jpg" \
  -F "requestId=req-menu-board-1"
```

6) 음식 이미지 분석
```bash
curl -X POST "$PY_BASE/api/v1/ai/food-images/analyze" \
  -H "$COMMON_HEADER_LANG" \
  -F "image=@/absolute/path/food.jpg" \
  -F "requestId=req-food-1"
```

#### 3-7. Java DTO 바인딩 체크리스트

Spring Boot에서 Python 응답을 DTO로 매핑할 때, 아래 항목을 점검하세요.

| 점검 항목 | 확인 기준 |
| --- | --- |
| 루트 래핑 | 모든 응답이 `success`, `data`(성공) / `success`, `code`, `msg`(실패) 구조인지 |
| 필드명 일치 | JSON key와 Java record 필드명(camelCase)이 정확히 일치하는지 |
| 날짜 파싱 | `startDate`, `endDate`, `mealDate`는 `LocalDate`, `analyzedAt`는 `OffsetDateTime` 또는 `String`으로 수용 가능한지 |
| menuId 상관관계 | 요청 `menuId`가 응답 `results[].menuId`로 그대로 반환되는지 |
| ingredients 타입 | `ingredientCode`는 `String`, `confidence`는 `BigDecimal` 또는 `Double`로 매핑되는지 |
| 빈 배열 처리 | 실패/미탐지 시 `ingredients`, `translations`, `meals`가 빈 배열로 와도 정상 처리되는지 |
| 실패 응답 처리 | `success=false`일 때 `code/msg`를 예외/에러 응답으로 변환하는 공통 로직이 있는지 |
| 언어 헤더 | `Accept-Language`가 `ko`, `en`, `zh-CN`, `vi`, `ja` 및 locale 변형(`en-US`)에서 동작하는지 |
| 이미지 업로드 | `multipart/form-data` 요청 시 파일 키 이름이 정확히 `image`인지 |
| 타임아웃/재시도 | Python 호출용 `RestClient/WebClient`에 타임아웃·재시도 정책이 적용되어 있는지 |

권장 DTO 루트 예시
```java
public record ApiSuccessResponse<T>(
    boolean success,
    T data
) {}

public record ApiErrorResponse(
    boolean success,
    String code,
    String msg
) {}
```

## 환경변수 정리

### 필수
- `GEMINI_API_KEY`
- `SPRING_MENUS_URL`
- `SPRING_IMAGE_IDENTIFY_URL`
- `SPRING_TEXT_ANALYSIS_URL`

### 선택
- `SPRING_IMAGE_ANALYSIS_URL` (직접 이미지 상세분석 사용 시)
- `SPRING_API_TOKEN`, `SPRING_API_KEY`
- `GEMINI_MODEL`, `WEEKLY_MENU_MODEL`
- `I18N_LOCALE` (기본 `en`)
- `WEEKLY_CRAWL_DAY`, `WEEKLY_CRAWL_HOUR`, `WEEKLY_CRAWL_MINUTE`
- `WEEKLY_MENU_BATCH_SIZE`, `WEEKLY_MENU_SLEEP_SECONDS`
- `SERVICE_TIMEZONE` (기본 `Asia/Seoul`)
- `ENABLE_DIRECT_IMAGE_ANALYSIS` (기본 `false`)
- `CRAWL_SOURCE_ALLOWLIST`
  - `service_ops.py`의 `load_menu_table_for_source()`에서 `sourceUrl` 허용 host를 제한하는 SSRF 방어 설정
  - 형식: 쉼표(,)로 구분한 hostname 목록 (예: `CRAWL_SOURCE_ALLOWLIST=www.kumoh.ac.kr,kumoh.ac.kr`)
  - 기본값(미설정): 코드 기본 allowlist(`www.kumoh.ac.kr`, `kumoh.ac.kr`)만 허용

## Spring Boot DTO 가이드

### 1) 이미지 식별 결과 수신 DTO (`SPRING_IMAGE_IDENTIFY_URL`)
```json
{
  "requestId": "req-1",
  "capturedAt": "2026-04-07T12:00:00+09:00",
  "identified": {
    "foodNameKo": "김치볶음밥",
    "confidence": 0.93
  }
}
```

### 2) 텍스트 분석 결과 수신 DTO (`SPRING_TEXT_ANALYSIS_URL`)
```json
{
  "foodNameInput": "김치볶음밥",
  "capturedAt": "2026-04-07T12:00:05+09:00",
  "analysis": {
    "foodNameKo": "김치볶음밥",
    "ingredientsKo": ["쌀", "김치", "계란"],
    "allergensKo": [
      {"name": "난류", "reason": "계란 토핑 가능성"},
      {"name": "대두", "reason": "소스/양념 사용 가능성"}
    ]
  }
}
```

### 3) 주간 메뉴 통합 전송 DTO (`SPRING_MENUS_URL`)
```json
{
  "source": "https://www.kumoh.ac.kr",
  "capturedAt": "2026-04-07T03:00:00+00:00",
  "restaurants": [
    {"name": "학생식당", "columns": ["월(04.07)"], "rows": [["..."]]}
  ],
  "i18nSummary": {
    "locale": "en",
    "disclaimer": "AI-estimated allergy guidance.",
    "items": [
      {
        "restaurant": "학생식당",
        "dayColumn": "월(04.07)",
        "menuTextKo": "김치볶음밥",
        "menuSummaryEn": "Kimchi fried rice set",
        "allergyNotesEn": "May contain egg and soy."
      }
    ]
  }
}
```

### Java record 예시
```java
public record IdentifyIngestRequest(
    String requestId,
    String capturedAt,
    Map<String, Object> identified
) {}

public record FoodTextAnalysisIngestRequest(
    String foodNameInput,
    String capturedAt,
    Map<String, Object> analysis
) {}

public record MenuIngestRequest(
    String source,
    String capturedAt,
    List<RestaurantMenu> restaurants,
    Map<String, Object> i18nSummary
) {}

public record RestaurantMenu(
    String name,
    List<String> columns,
    List<List<String>> rows
) {}
```

`identified`/`analysis`는 모델 출력 변경 가능성이 있어 `Map<String, Object>` 또는 `JsonNode`를 권장합니다.

## AWS 배포

배포 파일은 `deploy/aws/`를 사용합니다.

### 1) EC2에서 실행
```bash
cp deploy/aws/.env.live.example .env
vi .env
sudo bash deploy/aws/setup_live_service.sh \
  --repo-dir /home/ec2-user/AI-Agent-Crawler \
  --run-user ec2-user \
  --port 8000
```

### 2) 상태/로그
```bash
sudo systemctl status ai-crawler-live
sudo journalctl -u ai-crawler-live -f
curl http://127.0.0.1:8000/health
```

### 3) Nginx (선택)
```bash
sudo cp deploy/aws/nginx-live-service.conf /etc/nginx/conf.d/ai-crawler-live.conf
sudo nginx -t
sudo systemctl restart nginx
```

## 운영 체크리스트

- Python 서비스는 내부망/보안그룹으로 Spring 서버에서만 접근 가능하게 제한
- `SPRING_API_TOKEN` 설정 시 `/crawl-and-forward` Bearer 인증 사용
- `ENABLE_DIRECT_IMAGE_ANALYSIS`는 필요할 때만 `true`
- Gemini quota 제한을 고려해 `WEEKLY_MENU_BATCH_SIZE`, `WEEKLY_MENU_SLEEP_SECONDS` 조정
- 장애 시 `journalctl` 로그와 Spring 수신 로그를 함께 확인

## 참고

- CSV·이미지 경로는 **실행 시 현재 작업 디렉터리** 기준입니다. 루트에서 실행하면 `menu_allergy_gemini.csv`, `test_image.jpeg` 등이 그대로 맞습니다.

---