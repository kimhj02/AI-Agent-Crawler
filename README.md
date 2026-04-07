# AI-Agent-Crawler

Gemini API와 Python으로 금오공대 급식표를 수집·분석합니다.

## 프로젝트 구조

| 폴더 | 설명 |
|------|------|
| `crawler/` | 급식표 HTML 크롤링, Spring Boot 전송(`push_menus`) |
| `menu_allergy/` | 메뉴 문구 기반 재료·알레르기 추정 (Gemini) |
| `food_image/` | 음식 이미지 기반 식재료 추정 (Gemini Vision) |

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

## 참고

- CSV·이미지 경로는 **실행 시 현재 작업 디렉터리** 기준입니다. 루트에서 실행하면 `menu_allergy_gemini.csv`, `test_image.jpeg` 등이 그대로 맞습니다.
