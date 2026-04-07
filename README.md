# AI-Agent-Crawler

Gemini API와 Python으로 금오공대 급식표를 수집·분석합니다.

## 프로젝트 구조

| 폴더 | 설명 |
|------|------|
| `crawler/` | 급식표 HTML 크롤링 |
| `menu_allergy/` | 메뉴 문구 기반 재료·알레르기 추정 (Gemini) |
| `food_image/` | 음식 이미지 기반 식재료 추정 (Gemini Vision) |

## 준비

```bash
pip install -r requirements.txt
```

Gemini를 쓰는 스크립트는 API 키가 필요합니다.

```bash
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

## 참고

- CSV·이미지 경로는 **실행 시 현재 작업 디렉터리** 기준입니다. 루트에서 실행하면 `menu_allergy_gemini.csv`, `test_image.jpeg` 등이 그대로 맞습니다.
