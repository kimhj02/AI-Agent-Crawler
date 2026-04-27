# AI-Agent-Crawler

Gemini API와 Python으로 금오공대 급식표를 수집/분석하고, Spring Boot와 연동하는 서비스입니다.

## 현재 구조 (최신)

리팩터링 이후 구조는 `app` 중심 + `scripts`/`tests` 분리 방식입니다.

| 경로 | 설명 |
|---|---|
| `app/config` | 런타임 설정, FastAPI 앱 팩토리 |
| `app/controller` | API 라우터(FastAPI) |
| `app/service` | 유스케이스 서비스 |
| `app/repository` | 외부 I/O 연동 계층 |
| `app/domain` | 도메인 로직 (crawler/image/allergy) |
| `app/dto` | 요청/응답 모델 |
| `app/util` | 서비스 공통 유틸 |
| `scripts` | CLI 실행 엔트리 |
| `tests` | 테스트 코드 |
| `user_features` | 확장 기능(알레르기 필터, i18n payload 등) |

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

레거시 호환 API:

- `GET /health`
- `POST /crawl-and-forward`
- `POST /identify-image-and-forward`
- `POST /analyze-food-text-and-forward`
- `POST /analyze-image-and-forward`

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

## 운영 참고

- `ENABLE_DIRECT_IMAGE_ANALYSIS=true`일 때만 직접 이미지 상세분석 API 사용
- `CRAWL_SOURCE_ALLOWLIST`로 크롤링 source host 제한 가능
- Gemini 호출량에 맞춰 `WEEKLY_MENU_BATCH_SIZE`, `WEEKLY_MENU_SLEEP_SECONDS` 조정 권장
