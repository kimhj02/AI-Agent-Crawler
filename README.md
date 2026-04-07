# AI-Agent-Crawler

Gemini API와 Python으로 금오공대 급식표를 수집·분석합니다.

## 프로젝트 구조

| 폴더 | 설명 |
|------|------|
| `crawler/` | 급식표 HTML 크롤링, Spring Boot 전송(`push_menus`) |
| `menu_allergy/` | 메뉴 문구 기반 재료·알레르기 추정 (Gemini) |
| `food_image/` | 음식 이미지 기반 식재료 추정 (Gemini Vision) |
| `user_features/` | 알레르기 필터, 다국어 요약, 확장 Spring 페이로드 |

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
python -m uvicorn user_features.live_service:app --host 0.0.0.0 --port 8000
```

### 2) 상태 확인
```bash
curl http://localhost:8000/health
```

### 3) 주요 API
- `GET /health`
- `POST /crawl-and-forward` (Bearer 인증: `SPRING_API_TOKEN` 설정 시 필수)
- `POST /identify-image-and-forward`
- `POST /analyze-food-text-and-forward`
- `POST /analyze-image-and-forward` (옵션, 기본 비활성화)

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

이 저장소의 일부 문서·코드는 [Cursor](https://cursor.com) 로 편집·보조 작성되었습니다.
