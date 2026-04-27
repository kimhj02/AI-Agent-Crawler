# AI-Agent-Crawler 계층 구조

리팩터링 이후 코드 탐색 기준은 아래와 같습니다.

## 계층 가이드

- `app/controller`
  - FastAPI 라우터와 HTTP 입출력 처리
  - 요청 검증, 서비스 호출, 응답 변환
- `app/service`
  - 유스케이스 오케스트레이션
  - 라우터의 비즈니스 루프/동시성 처리 담당
- `app/repository`
  - 외부 I/O (Spring HTTP, 크롤링 소스, Gemini 호출)
- `app/domain`
  - 순수 도메인 모델 및 정책
- `app/dto`
  - 요청/응답 스키마 모델
- `app/config`
  - 런타임 설정 및 앱 팩토리

## 호환성 정책

- 기존 경로(`user_features/live/*`, `user_features/live_service.py`)는 깨지지 않도록 유지합니다.
- 신규 개발은 `app/*`를 우선 참조합니다.

## 실행 엔트리

- API 서버: `python3 -m uvicorn user_features.live_service:app --host 0.0.0.0 --port 8000`
- CLI: `scripts/` 하위 파일 사용 권장
