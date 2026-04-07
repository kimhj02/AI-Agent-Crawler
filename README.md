# AI-Agent-Crawler

Gemini API와 Python으로 금오공대 급식표를 수집·분석합니다.

## 프로젝트 구조

| 폴더 | 설명 |
|------|------|
| `crawler/` | 급식표 HTML 크롤링, Spring Boot 전송(`push_menus`) |
| `menu_allergy/` | 메뉴 문구 기반 재료·알레르기 추정 (Gemini) |
| `food_image/` | 음식 이미지 기반 식재료 추정 (Gemini Vision) |
| `user_features/` | 알레르기 필터, 다국어 요약, 확장 Spring 페이로드 |

## 준비

```bash
pip install -r requirements.txt
cp .env.example .env
```

`.env`에 비밀 값을 넣습니다(이 파일은 Git에 올라가지 않습니다). `menu_allergy`, `food_image`, `crawler.push_menus` 실행 시 **저장소 루트의 `.env`**를 자동으로 읽습니다.

Gemini를 쓰는 스크립트는 API 키가 필요합니다.

```bash
# .env 안에 GEMINI_API_KEY=... 입력하거나, 터미널에서:
export GEMINI_API_KEY='여기에_키'
```

선택: 모델 변경

```bash
export GEMINI_MODEL='gemini-2.5-flash-lite'   # 메뉴 분석 기본과 맞출 때
# 또는 food_image는 기본이 gemini-2.5-flash (--model 으로도 지정 가능)
```

## 실행 방법

**저장소 루트 디렉터리**에서 아래처럼 실행합니다 (`python -m`이 프로젝트 패키지를 찾을 수 있도록).

### 1. 급식표만 수집 (크롤링)

```bash
python -m crawler.crawl_menus
```

### 2. 메뉴·알레르기 분석 → CSV 저장

```bash
python -m menu_allergy.agent
```

자주 쓰는 옵션:

```bash
python -m menu_allergy.agent -n 4 --print-preview          # 소량 테스트 + 미리보기
python -m menu_allergy.agent -o 결과.csv                    # 출력 파일 지정
python -m menu_allergy.agent --batch-size 4 --sleep 21     # 배치 크기·대기(초)
python -m menu_allergy.agent --help
```

### 3. 음식 이미지 분석

```bash
python -m food_image.agent
```

기본 이미지는 루트의 `test_image.jpeg`입니다. 다른 파일을 넣을 때:

```bash
python -m food_image.agent path/to/photo.jpg
python -m food_image.agent path/to/photo.jpg --ingredients-table
python -m food_image.agent --help
```

### 4. 크롤링 결과를 Spring Boot 서버로 전송

크롤링 직후 같은 JSON 페이로드를 `POST`합니다. URL·토큰은 인자 또는 환경 변수로 줄 수 있습니다.

```bash
export SPRING_MENUS_URL='http://localhost:8080/api/menus/ingest'
# 선택: Bearer 토큰
export SPRING_API_TOKEN='...'
# 또는 API 키 헤더 (서버에서 X-API-Key 검증 시)
export SPRING_API_KEY='...'

python -m crawler.push_menus
```

미리 본문만 확인:

```bash
python -m crawler.push_menus --dry-run --indent 2
```

한 줄로 URL만 지정:

```bash
python -m crawler.push_menus --url http://localhost:8080/api/menus/ingest
python -m crawler.push_menus --help
```

**요청 JSON 형식** (서버 DTO와 맞추면 됩니다):

- `source` (string): 출처 URL 등
- `capturedAt` (string): UTC ISO-8601 수집 시각
- `restaurants` (array): 식당별
  - `name`: 식당 이름 (예: `학생식당`)
  - `columns`: 요일·구분 열 제목 배열
  - `rows`: 각 행의 셀 문자열 배열 (`columns` 순서와 동일)

**Spring Boot 수신 예시** (경로·검증은 프로젝트에 맞게 수정):

```java
// build.gradle: implementation 'org.springframework.boot:spring-boot-starter-web'

import org.springframework.web.bind.annotation.*;
import java.time.Instant;
import java.util.List;

@RestController
@RequestMapping("/api/menus")
public class MenuIngestController {

    public record RestaurantMenu(String name, List<String> columns, List<List<String>> rows) {}
    public record MenuIngestRequest(String source, String capturedAt, List<RestaurantMenu> restaurants) {}

    @PostMapping("/ingest")
    public void ingest(@RequestBody MenuIngestRequest body) {
        Instant.parse(body.capturedAt()); // 필요 시 검증
        // TODO: DB 저장 등
    }
}
```

CORS가 필요하면 `@CrossOrigin` 또는 `WebMvcConfigurer`로 허용 origin을 설정하세요. 다른 경로·필드명을 쓰는 경우 Python 쪽 `crawler/spring_payload.py`의 키를 서버와 동일하게 맞추면 됩니다.

### 5~7. 사용자 기능 (`user_features/`)

외국인·알레르기 사용자를 위한 기능입니다. **먼저 2번**으로 `menu_allergy_gemini.csv` 같은 분석 파일을 만든 뒤 사용하는 것이 일반적입니다.

| 구성 요소 | 하는 일 (한 줄) |
|-----------|-----------------|
| `allergen_catalog.py` | 식약처 표시 대상 알레르기 **표준 이름(canonical)** 과 **별칭**(계란→난류, milk→우유 등), 요약문 매칭용 **키워드** 정리 |
| `allergy_filter.py` | 위 CSV에서 사용자가 고른 알레르기에 **걸리는 메뉴만** 골라 표/JSON 출력 |
| `i18n_summary.py` | 같은 CSV를 Gemini에 넘겨 **영어 등** 메뉴·알레르기 안내 JSON 생성 (의료 단정 아님) |
| `payloads.py` | 크롤 원본 JSON + `userAllergensKo` + `avoidMenus` + (선택) `i18nSummary` 를 **한 덩어리**로 만듦 |
| `push_extended.py` | 위 덩어리를 **Spring으로 POST** (크롤 + 분석 + 선택 i18n 한 번에) |

**데이터 흐름 (개념):**

```
[2번 CSV] ──► allergy_filter  → "피해야 할 메뉴" 표 또는 JSON
     │
     ├──► i18n_summary        → 외국인용 요약 JSON 파일
     │
     └──► push_extended       → Spring 서버 (원본 급식 + 필터 + 선택 i18n)
```

#### 5. 알레르기 필터 (CLI: `allergy_filter`)

- **입력:** `menu_allergy` 결과 CSV (`알레르기_요약` 열 필수)
- **출력:** 콘솔 표, 또는 `--json` 시 API에 넣기 좋은 `userAllergensKo` + `avoidMenus`
- **옵션:** `--today-only` → 한국(서울) 기준 **오늘 요일 열**만 대상

```bash
python -m user_features.allergy_filter --list-allergens

python -m user_features.allergy_filter --csv menu_allergy_gemini.csv --allergens 우유,대두,난류

python -m user_features.allergy_filter --csv menu_allergy_gemini.csv --allergens 우유 --today-only

python -m user_features.allergy_filter --csv menu_allergy_gemini.csv --allergens 우유,밀 --json
```

#### 6. 다국어 요약 (CLI: `i18n_summary`, Gemini 필요)

- **입력:** 분석 CSV (행 수는 `--limit`으로 제한)
- **출력:** `locale`, `disclaimer`, `items[]` 등이 담긴 JSON (영어 위주, `--locale`으로 태그 지정)

```bash
python -m user_features.i18n_summary --csv menu_allergy_gemini.csv --locale en --limit 20 -o i18n_menu_en.json
python -m user_features.i18n_summary --help
```

#### 7. 확장 페이로드 POST (CLI: `push_extended`)

- **하는 일:** 지금 급식표를 크롤한 뒤, 분석 CSV·사용자 알레르기·(선택) i18n을 합쳐 서버로 보냄
- **사전 준비:** `SPRING_MENUS_URL` 등은 4번과 동일. `--with-i18n` 쓰면 `GEMINI_API_KEY` 필요

```bash
python -m user_features.push_extended --dry-run --analysis-csv menu_allergy_gemini.csv --allergens 우유,대두

python -m user_features.push_extended --url http://localhost:8080/api/menus/ingest \
  --analysis-csv menu_allergy_gemini.csv --allergens 우유 --with-i18n --i18n-locale en
```

**Spring 쪽 JSON에 추가로 실릴 수 있는 필드 (예시):** `userAllergensKo`, `avoidMenus`(영문 키), `i18nSummary`(객체). 서버 DTO는 팀 규칙에 맞게 확장하면 됩니다.

### 8. 상시 서비스 모드 (주간 크롤링 + 실시간 이미지 분석)

Spring에서 실시간 이미지 분석을 호출하려면 Python도 API 서버로 상시 구동해야 합니다.

```bash
pip install -r requirements.txt
```

`.env` 예시:

```bash
SPRING_MENUS_URL=http://localhost:8080/api/menus/ingest
SPRING_IMAGE_ANALYSIS_URL=http://localhost:8080/api/image-analysis/ingest
GEMINI_API_KEY=...

# 선택: 인증
SPRING_API_TOKEN=...
# SPRING_API_KEY=...

# 선택: 주간 크롤링 시각 (기본: mon 06:00, Asia/Seoul)
WEEKLY_CRAWL_DAY=mon
WEEKLY_CRAWL_HOUR=6
WEEKLY_CRAWL_MINUTE=0
SERVICE_TIMEZONE=Asia/Seoul
```

실행:

```bash
python -m uvicorn user_features.live_service:app --host 0.0.0.0 --port 8000
```

API:

- `GET /health`: 상태 확인
- `POST /crawl-and-forward`: 즉시 크롤링 + Gemini 메뉴/알레르기 분석 + i18n(영문 등) 생성 후 `SPRING_MENUS_URL`로 전송
- `POST /analyze-image-and-forward`: multipart 파일(`image`)을 Gemini로 분석 후 `SPRING_IMAGE_ANALYSIS_URL`로 전송
  - 기본 비활성화. `ENABLE_DIRECT_IMAGE_ANALYSIS=true`일 때만 사용
  - 선택 파라미터: `user_id`, `request_id`
- `POST /identify-image-and-forward`: multipart 파일(`image`)에서 음식 이름만 식별해 `SPRING_IMAGE_IDENTIFY_URL`로 전송
- `POST /analyze-food-text-and-forward`: Spring이 텍스트 음식명을 넘기면 재료/알레르기 분석 후 `SPRING_TEXT_ANALYSIS_URL`로 전송

서비스가 올라가 있으면 내부 스케줄러가 주 1회 크롤링 전송을 자동 실행합니다.

AWS 배포용 스크립트/템플릿은 `deploy/aws/`를 참고하세요.

## 참고

- CSV·이미지 경로는 **실행 시 현재 작업 디렉터리** 기준입니다. 루트에서 실행하면 `menu_allergy_gemini.csv`, `test_image.jpeg` 등이 그대로 맞습니다.

---

이 저장소의 일부 문서·코드는 [Cursor](https://cursor.com) 로 편집·보조 작성되었습니다.
