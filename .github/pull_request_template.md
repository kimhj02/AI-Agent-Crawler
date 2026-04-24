## Summary
- 
- 
- 

## Why
- 

## Changes
- [ ] API/라우터 변경
- [ ] 서비스/리포지터리 리팩터링
- [ ] 문서 업데이트
- [ ] 테스트 추가/수정

## Test Plan
- [ ] `python3 -m pytest -q tests/live`
- [ ] 로컬 FastAPI 실행 후 주요 엔드포인트 수동 호출
- [ ] (필요 시) Spring 연동 시나리오 점검

## API Compatibility
- [ ] 기존 엔드포인트 호환 유지
- [ ] 비호환 변경 없음
- [ ] 비호환 변경 있음 (아래 기재)

비호환 변경 상세:
- 

## Risks / Rollback
- 위험요소:
  - 
- 롤백방법:
  - 이전 브랜치/커밋으로 복구 후 재배포

## Checklist
- [ ] 민감정보(API 키/토큰) 커밋 여부 확인
- [ ] 에러 코드/응답 포맷 확인
- [ ] README 또는 운영 문서 업데이트
