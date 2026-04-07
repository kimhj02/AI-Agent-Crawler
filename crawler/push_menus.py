#!/usr/bin/env python3
"""크롤링한 급식 데이터를 Spring Boot(또는 호환 REST) 서버로 전송합니다."""

from __future__ import annotations

import argparse
import json
import os
import sys

import requests

import repo_env
from crawler.kumoh_menu import load_menus
from crawler.spring_payload import build_menu_ingest_payload


def post_menu_ingest(
    url: str,
    payload: dict,
    *,
    bearer_token: str | None = None,
    api_key: str | None = None,
    timeout: float = 60.0,
) -> requests.Response:
    headers = {"Content-Type": "application/json; charset=utf-8", "Accept": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    if api_key:
        headers["X-API-Key"] = api_key
    return requests.post(url, json=payload, headers=headers, timeout=timeout)


def main() -> None:
    repo_env.load_dotenv_from_repo_root()

    parser = argparse.ArgumentParser(
        description="급식표 크롤링 후 Spring Boot 서버로 POST",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("SPRING_MENUS_URL", "").strip() or None,
        help="수신 URL (예: http://localhost:8080/api/menus/ingest). 생략 시 환경변수 SPRING_MENUS_URL",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="전송하지 않고 JSON만 stdout에 출력",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=None,
        help="--dry-run 시 JSON 들여쓰기 칸 수 (예: 2)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP 타임아웃(초)",
    )
    parser.add_argument(
        "--source",
        default="https://www.kumoh.ac.kr",
        help="페이로드 source 필드",
    )
    args = parser.parse_args()

    menus = load_menus()
    if not menus:
        print("크롤링 결과가 비었습니다.", file=sys.stderr)
        raise SystemExit(1)

    payload = build_menu_ingest_payload(menus, source=args.source)

    if args.dry_run:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=args.indent)
        if args.indent is not None:
            sys.stdout.write("\n")
        return

    if not args.url:
        raise SystemExit(
            "POST할 URL이 없습니다. --url 또는 환경변수 SPRING_MENUS_URL(.env 가능)을 설정하세요."
        )

    token = os.environ.get("SPRING_API_TOKEN", "").strip() or None
    api_key = os.environ.get("SPRING_API_KEY", "").strip() or None

    try:
        res = post_menu_ingest(
            args.url,
            payload,
            bearer_token=token,
            api_key=api_key,
            timeout=args.timeout,
        )
    except requests.RequestException as e:
        print(f"요청 실패: {e}", file=sys.stderr)
        raise SystemExit(1) from e

    print("HTTP", res.status_code)
    body = (res.text or "").strip()
    if not res.ok and body:
        print(body[:8000])
        if len(body) > 8000:
            print("... (응답 잘림)")

    if not res.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
