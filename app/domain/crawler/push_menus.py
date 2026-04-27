#!/usr/bin/env python3
"""크롤링한 급식 데이터를 Spring Boot(또는 호환 REST) 서버로 전송합니다."""

from __future__ import annotations

import argparse
import json
import os
import sys

import requests

import repo_env
from app.domain.crawler.kumoh_menu import load_menus
from app.domain.crawler.spring_payload import (
    build_menu_ingest_payload,
    build_menu_ingest_swagger_payload,
)


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
    parser = argparse.ArgumentParser(description="급식표 크롤링 후 Spring Boot 서버로 POST")
    parser.add_argument("--url", default=os.environ.get("SPRING_MENUS_URL", "").strip() or None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--indent", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--source", default="https://www.kumoh.ac.kr")
    parser.add_argument("--legacy-format", action="store_true")
    args = parser.parse_args()

    menus = load_menus()
    if not menus:
        print("크롤링 결과가 비었습니다.", file=sys.stderr)
        raise SystemExit(1)
    if args.legacy_format:
        payload = build_menu_ingest_payload(menus, source=args.source)
    else:
        payload = build_menu_ingest_swagger_payload(menus, source=args.source)

    if args.dry_run:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=args.indent)
        if args.indent is not None:
            sys.stdout.write("\n")
        return
    if not args.url:
        raise SystemExit("POST할 URL이 없습니다. --url 또는 SPRING_MENUS_URL을 설정하세요.")
    token = os.environ.get("SPRING_API_TOKEN", "").strip() or None
    api_key = os.environ.get("SPRING_API_KEY", "").strip() or None
    res = post_menu_ingest(args.url, payload, bearer_token=token, api_key=api_key, timeout=args.timeout)
    print("HTTP", res.status_code)
    body = (res.text or "").strip()
    if not res.ok and body:
        print(body[:8000])
    if not res.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
