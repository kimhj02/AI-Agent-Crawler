"""Spring 호환 API 회귀 스모크 테스트 스크립트.

기본 동작:
- uvicorn 서버를 자동 실행
- 핵심 엔드포인트 호출
- 성공/실패 케이스 검증
- 서버 자동 종료
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any

import requests


def _pretty(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return str(data)


def _request(method: str, url: str, **kwargs):
    return requests.request(method=method, url=url, timeout=30, **kwargs)


def _wait_for_server(base_url: str, timeout_sec: int = 25) -> None:
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            resp = _request("GET", f"{base_url}/health")
            if resp.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("서버 시작 대기 시간 초과")


def _assert_status(resp: requests.Response, expected_status: int, label: str) -> None:
    if resp.status_code != expected_status:
        body = ""
        try:
            body = _pretty(resp.json())
        except Exception:
            body = (resp.text or "")[:500]
        raise AssertionError(
            f"{label}: status={resp.status_code} expected={expected_status}\nresponse={body}"
        )


def run_suite(base_url: str) -> None:
    auth_headers = {"Authorization": "Bearer test-user-token"}

    tests = []

    # 정상 케이스
    tests.append(
        (
            "GET /health",
            _request("GET", f"{base_url}/health"),
            200,
        )
    )
    tests.append(
        (
            "POST /auth/login",
            _request(
                "POST",
                f"{base_url}/auth/login",
                json={"idToken": "dummy-id-token", "deviceId": "device-1"},
            ),
            200,
        )
    )
    tests.append(
        (
            "GET /api/v1/settings/language",
            _request("GET", f"{base_url}/api/v1/settings/language", headers=auth_headers),
            200,
        )
    )
    tests.append(
        (
            "PATCH /api/v1/settings/language",
            _request(
                "PATCH",
                f"{base_url}/api/v1/settings/language",
                headers=auth_headers,
                json={"languageCode": "en"},
            ),
            200,
        )
    )
    tests.append(
        (
            "GET /api/v1/settings/options/languages",
            _request("GET", f"{base_url}/api/v1/settings/options/languages", headers=auth_headers),
            200,
        )
    )
    tests.append(
        (
            "POST /api/v1/onboarding/complete",
            _request(
                "POST",
                f"{base_url}/api/v1/onboarding/complete",
                headers=auth_headers,
                json={
                    "languageCode": "en",
                    "schoolId": 1,
                    "allergyCodes": ["EGG"],
                    "religiousCode": "HALAL",
                },
            ),
            200,
        )
    )
    tests.append(
        (
            "GET /api/v1/mealcrawl/cafeterias",
            _request("GET", f"{base_url}/api/v1/mealcrawl/cafeterias", headers=auth_headers),
            200,
        )
    )
    tests.append(
        (
            "GET /api/v1/mealcrawl/weekly-meals",
            _request(
                "GET",
                f"{base_url}/api/v1/mealcrawl/weekly-meals",
                headers=auth_headers,
                params={"cafeteriaId": 1, "weekStartDate": "2026-04-27"},
            ),
            (200, 502),
        )
    )

    # 실패 케이스
    tests.append(
        (
            "GET /api/v1/settings/language (no auth)",
            _request("GET", f"{base_url}/api/v1/settings/language"),
            401,
        )
    )
    tests.append(
        (
            "PATCH /api/v1/settings/language (invalid code)",
            _request(
                "PATCH",
                f"{base_url}/api/v1/settings/language",
                headers={"Authorization": "Bearer x"},
                json={"languageCode": "xx"},
            ),
            400,
        )
    )

    passed = 0
    for label, resp, expected in tests:
        if isinstance(expected, tuple):
            if resp.status_code not in expected:
                _assert_status(resp, expected[0], label)
        else:
            _assert_status(resp, expected, label)
        print(f"[PASS] {label} -> {resp.status_code}")
        passed += 1

    print(f"\n총 {passed}건 테스트 통과")


def main() -> int:
    parser = argparse.ArgumentParser(description="Spring 호환 API 회귀 스모크 테스트")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--use-existing-server",
        action="store_true",
        help="이미 실행 중인 서버를 사용하고 자동 기동/종료를 하지 않습니다.",
    )
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    server_proc = None

    try:
        if not args.use_existing_server:
            server_proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "user_features.live_service:app",
                    "--host",
                    args.host,
                    "--port",
                    str(args.port),
                ],
                env={
                    **os.environ,
                    "ENABLE_SPRING_COMPAT_ROUTER": "true",
                    "SPRING_COMPAT_STUB_MODE": "true",
                },
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _wait_for_server(base_url)
            print("서버 자동 기동 완료")

        run_suite(base_url)
        return 0
    except Exception as exc:
        print(f"[FAIL] {exc}")
        return 1
    finally:
        if server_proc is not None:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()
            print("서버 자동 종료 완료")


if __name__ == "__main__":
    raise SystemExit(main())
